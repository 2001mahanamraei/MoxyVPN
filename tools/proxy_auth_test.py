"""Checks which Proxy-Authorization styles Mozilla's VPN proxy accepts.

Why: a standalone Chrome extension can only send Basic proxy credentials.
If the proxy refuses Basic, the extension cannot work without a desktop helper.

Usage (uses your saved MoxyVPN / foxyvpn login):
    python proxy_auth_test.py            # US server
    python proxy_auth_test.py de         # another country code

Your token is never printed.
"""
import base64
import socket
import ssl
import sys

import h2.config
import h2.connection
import h2.events

TARGET = "example.com:443"


def h2_connect(host, port, extra, verify=True, timeout=10):
    """Send one HTTP/2 CONNECT and return (alpn, status, headers)."""
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    ctx.set_alpn_protocols(["h2"])
    raw = socket.create_connection((host, port), timeout=timeout)
    tls = ctx.wrap_socket(raw, server_hostname=host)
    alpn = tls.selected_alpn_protocol()
    try:
        conn = h2.connection.H2Connection(config=h2.config.H2Configuration(client_side=True))
        conn.initiate_connection()
        tls.sendall(conn.data_to_send())
        sid = conn.get_next_available_stream_id()
        conn.send_headers(sid, [(":method", "CONNECT"), (":authority", TARGET)] + extra)
        tls.sendall(conn.data_to_send())
        while True:
            data = tls.recv(65536)
            if not data:
                return alpn, None, {"error": "connection closed"}
            for ev in conn.receive_data(data):
                if isinstance(ev, h2.events.ResponseReceived):
                    hdrs = {}
                    for k, v in ev.headers:
                        k = k.decode() if isinstance(k, bytes) else k
                        v = v.decode() if isinstance(v, bytes) else v
                        hdrs.setdefault(k.lower(), []).append(v)
                    return alpn, hdrs.get(":status", ["?"])[0], hdrs
                if isinstance(ev, (h2.events.StreamReset, h2.events.ConnectionTerminated)):
                    return alpn, None, {"error": type(ev).__name__}
            tls.sendall(conn.data_to_send())
    finally:
        try:
            tls.close()
        except OSError:
            pass


def b64(text):
    return base64.b64encode(text.encode()).decode()


def run_tests(host, port, jwt, verify=True):
    tests = [
        ("no credentials", []),
        ("Bearer (what the Mozilla VPN client sends)", [("proxy-authorization", "Bearer " + jwt)]),
        ("Basic  user='' password=<token>", [("proxy-authorization", "Basic " + b64(":" + jwt))]),
        ("Basic  user=<token> password=''", [("proxy-authorization", "Basic " + b64(jwt + ":"))]),
        ("Basic  user='token' password=<token>", [("proxy-authorization", "Basic " + b64("token:" + jwt))]),
    ]
    results = {}
    print(f"Proxy under test: {host}:{port}\n")
    for name, extra in tests:
        try:
            alpn, status, hdrs = h2_connect(host, port, extra, verify=verify)
        except Exception as exc:  # noqa: BLE001
            print(f"[{name}]\n   error: {type(exc).__name__}: {exc}\n")
            results[name] = None
            continue
        chall = hdrs.get("proxy-authenticate", [])
        print(f"[{name}]\n   alpn={alpn}  status={status}"
              + (f"  proxy-authenticate={chall}" if chall else "")
              + (f"  note={hdrs.get('error')}" if "error" in hdrs else ""))
        print()
        results[name] = status
    basic_ok = any(str(results.get(n)) == "200" for n in results if n.startswith("Basic"))
    bearer_ok = str(results.get("Bearer (what the Mozilla VPN client sends)")) == "200"
    print("=" * 60)
    print("Bearer works :", "YES" if bearer_ok else "NO (test itself is unreliable - send me this output)")
    print("Basic works  :", "YES - a standalone Chrome extension is possible" if basic_ok
          else "NO - Chrome cannot authenticate to this proxy on its own")
    return basic_ok


def main():
    country = (sys.argv[1] if len(sys.argv) > 1 else "us").lower()
    from foxyvpn import auth, guardian, proxystate, serverlist

    runtime = auth.obtain_auth()
    info = guardian.fetch_proxy_pass(guardian.GUARDIAN_ENDPOINT_DEFAULT, runtime.access_token)
    cands = proxystate._candidates_for_country(serverlist.fetch_server_list(), country)
    if not cands:
        sys.exit(f"No servers found for country '{country}'.")
    c = cands[0]
    run_tests(c.host, c.port, info.raw_token)


if __name__ == "__main__":
    main()
