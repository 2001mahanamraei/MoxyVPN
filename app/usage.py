"""Data-usage tracking: reads the Firefox VPN quota and remembers it between runs."""
import json
import os
import tempfile
import time
from datetime import datetime, timezone

STATE_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "MoxyVPN")
STATE_FILE = os.path.join(STATE_DIR, "state.json")
MAX_HISTORY = 200


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="state.", dir=STATE_DIR)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, STATE_FILE)
    except OSError:
        pass


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_reset(raw):
    """Reset time -> unix timestamp (or None). Accepts ISO text or epoch seconds/ms."""
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        n = int(raw)
        return n / 1000 if n > 10**11 else n
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def fetch_quota(api_proxy=None):
    """Ask Mozilla's Guardian for the account quota. Blocking; run in a thread.

    Returns {"limit","left","used","reset","fetched_at"} (values may be None).
    """
    from foxyvpn import auth, guardian
    from foxyvpn.exceptions import QuotaExceededError

    import builtins

    def _no_prompt(*_a, **_k):
        raise RuntimeError("login required - use First login")

    if api_proxy:
        from foxyvpn import http_client
        http_client.set_control_plane_proxy(api_proxy)
    endpoint = guardian.GUARDIAN_ENDPOINT_DEFAULT
    real_input, builtins.input = builtins.input, _no_prompt
    try:
        runtime = auth.obtain_auth()
    finally:
        builtins.input = real_input
    limit = left = reset = None
    subscribed = limited = None
    reached = False
    try:
        ent = guardian.fetch_user_info(endpoint, runtime.access_token)
        limit = _int(ent.max_bytes)
        subscribed = bool(ent.subscribed)
        limited = bool(ent.limited_bandwidth)
        reached = True
    except Exception:
        pass
    try:
        info = guardian.fetch_proxy_pass(endpoint, runtime.access_token)
        limit = _int(info.quota_max) or limit
        left = _int(info.quota_left)
        reset = parse_reset(info.quota_reset)
        reached = True
    except QuotaExceededError:
        left = 0
        reached = True
    except Exception:
        pass
    if not reached:
        raise RuntimeError("could not reach Mozilla's servers")
    email = None
    try:
        import httpx
        r = httpx.get("https://profile.accounts.firefox.com/v1/profile",
                      headers={"Authorization": "Bearer " + runtime.access_token},
                      proxy=api_proxy or None, timeout=15)
        if r.status_code == 200:
            email = r.json().get("email")
    except Exception:
        pass
    if left == 0 and limit:
        used = limit
    elif limit is not None and left is not None:
        used = max(limit - left, 0)
    else:
        used = None
    return {"limit": limit, "left": left, "used": used, "reset": reset, "fetched_at": time.time(),
            "subscribed": subscribed, "limited": limited, "email": email}


def remember(state, quota):
    """Store the latest quota and append to a small history log."""
    state["quota"] = quota
    if quota.get("email"):
        state["email"] = quota["email"]
    hist = state.setdefault("history", [])
    if quota.get("used") is not None and (not hist or hist[-1].get("used") != quota["used"]):
        hist.append({"t": quota["fetched_at"], "used": quota["used"]})
        del hist[:-MAX_HISTORY]
    save_state(state)


def fmt_bytes(n):
    if n is None:
        return "-"
    gb = n / 1024 ** 3
    if gb >= 1:
        return f"{gb:.2f} GB" if gb < 100 else f"{gb:.0f} GB"
    return f"{n / 1024 ** 2:.0f} MB"


def fmt_ago(ts):
    if not ts:
        return ""
    s = max(int(time.time() - ts), 0)
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{s // 60} min ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    return f"{s // 86400} d ago"


def fmt_reset(ts):
    if not ts:
        return ""
    d = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
    days = (d.date() - datetime.now().date()).days
    when = d.strftime("%b %d").replace(" 0", " ")
    return f"resets {when}" + (f" ({days}d)" if days > 0 else "")
