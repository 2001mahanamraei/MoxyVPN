"""Settings page (slides in from the right), account dialog and small prompts."""
import tkinter as tk
import webbrowser

import usage
from theme import C, mix

FONT = "Segoe UI"
SOURCE_URL = "https://github.com/Vauth/FoxyVPN"

DNS_LABELS = {"auto": "Automatic", "cloudflare": "Cloudflare (encrypted)",
              "google": "Google (encrypted)", "quad9": "Quad9 (encrypted)", "off": "Off (plain DNS)"}
THEME_LABELS = {"dark": "Dark", "light": "Light", "system": "Follow system"}


def button(parent, text, cmd, accent=False, danger=False):
    bg = C.ACCENT if accent else (mix(C.RED, C.BG, 0.82) if danger else C.BORDER)
    fg = "#1B0F05" if accent else (C.RED if danger else C.TEXT)
    return tk.Button(parent, text=text, command=cmd, relief="flat", bd=0, cursor="hand2", bg=bg, fg=fg,
                     activebackground=mix(bg, C.TEXT, 0.12), activeforeground=fg,
                     font=(FONT, 10, "bold" if accent or danger else "normal"), padx=14, pady=8)


class Switch(tk.Canvas):
    def __init__(self, parent, value, command, bg):
        super().__init__(parent, width=48, height=28, bg=bg, highlightthickness=0, cursor="hand2")
        self.value, self.command = bool(value), command
        self.bind("<Button-1>", self._click)
        self.draw()

    def draw(self):
        self.delete("all")
        col = C.ACCENT if self.value else C.BORDER
        self.create_oval(2, 3, 26, 25, fill=col, outline="")
        self.create_oval(22, 3, 46, 25, fill=col, outline="")
        self.create_rectangle(14, 3, 34, 25, fill=col, outline="")
        x = 34 if self.value else 14
        self.create_oval(x - 9, 5, x + 9, 23, fill="#FFFFFF" if self.value else C.MUTED, outline="")

    def _click(self, _e=None):
        self.value = not self.value
        self.draw()
        self.command(self.value)


def ask_text(app, title, label, initial="", validate=None, hint=""):
    """Modal single-line prompt. Returns the text, or None if cancelled."""
    top = tk.Toplevel(app)
    top.title(title)
    top.configure(bg=C.BG)
    top.resizable(False, False)
    top.transient(app)
    top.grab_set()
    result = {"v": None}
    tk.Label(top, text=title, bg=C.BG, fg=C.TEXT, font=(FONT, 13, "bold")).pack(anchor="w", padx=20, pady=(18, 2))
    tk.Label(top, text=label, bg=C.BG, fg=C.MUTED, font=(FONT, 10), wraplength=320,
             justify="left").pack(anchor="w", padx=20)
    var = tk.StringVar(value=initial)
    e = tk.Entry(top, textvariable=var, width=34, bg=C.CARD, fg=C.TEXT, insertbackground=C.TEXT, relief="flat",
                 font=(FONT, 11), highlightthickness=1, highlightbackground=C.BORDER, highlightcolor=C.ACCENT)
    e.pack(padx=20, pady=(12, 4), ipady=6, fill="x")
    e.focus_set()
    e.select_range(0, "end")
    err = tk.Label(top, text=hint, bg=C.BG, fg=C.DIM, font=(FONT, 9), wraplength=320, justify="left")
    err.pack(anchor="w", padx=20)

    def ok(_e=None):
        v = var.get().strip()
        msg = validate(v) if validate else None
        if msg:
            err.config(text=msg, fg=C.RED)
            return
        result["v"] = v
        top.destroy()

    row = tk.Frame(top, bg=C.BG)
    row.pack(fill="x", padx=20, pady=16)
    button(row, "Save", ok, accent=True).pack(side="right")
    button(row, "Cancel", top.destroy).pack(side="right", padx=8)
    top.bind("<Return>", ok)
    top.bind("<Escape>", lambda e: top.destroy())
    app.wait_window(top)
    return result["v"]


def popup_choice(widget, options, current, on_pick):
    m = tk.Menu(widget, tearoff=0, bg=C.CARD, fg=C.TEXT, activebackground=C.ACCENT,
                activeforeground="#1B0F05", bd=0, font=(FONT, 10))
    for key, label in options.items():
        m.add_command(label=("\u2713  " if key == current else "     ") + label,
                      command=lambda k=key: on_pick(k))
    m.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())


# ---------------------------------------------------------------- validators
def v_host(v):
    if v in ("127.0.0.1", "0.0.0.0", "localhost"):
        return None
    parts = v.split(".")
    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        return None
    return "Use 127.0.0.1 (this PC only) or 0.0.0.0 (share on your network)."


def v_port(v):
    return None if v.isdigit() and 1 <= int(v) <= 65535 else "Enter a port between 1 and 65535."


def v_edge(v):
    if not v:
        return None
    host, _, port = v.rpartition(":")
    return None if host and port.isdigit() else "Use host:port, e.g. us1.example.com:443"


def v_upstream(v):
    import tunconf
    return None if tunconf.parse_upstream(v) else "Use socks5://host:port or http://host:port"


def v_dns(v):
    return None if v.strip() else "Enter at least one DNS server (IP or https:// URL)."


def v_api_proxy(v):
    return None if (not v or "://" in v) else "Use a URL like socks5://127.0.0.1:10808"


# ---------------------------------------------------------------------- page
class SettingsPage(tk.Frame):
    def __init__(self, app):
        super().__init__(app, bg=C.BG)
        self.app = app
        top = tk.Frame(self, bg=C.BG)
        top.pack(fill="x", padx=14, pady=(14, 4))
        back = tk.Label(top, text="\u2190", font=(FONT, 20), fg=C.TEXT, bg=C.BG, cursor="hand2")
        back.pack(side="left")
        back.bind("<Button-1>", lambda e: app.close_settings())
        tk.Label(top, text="Settings", font=(FONT, 18, "bold"), fg=C.TEXT, bg=C.BG).pack(side="left", padx=12)

        body = tk.Frame(self, bg=C.BG)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg=C.BG, highlightthickness=0)
        sb = tk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=C.BG)
        win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(win, width=e.width))
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))
        self.fill()

    def _wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def refill(self):
        y = self.canvas.yview()[0]
        for w in self.inner.winfo_children():
            w.destroy()
        self.fill()
        self.update_idletasks()
        self.canvas.yview_moveto(y)

    # ---- row helpers
    def section(self, title, first=False):
        if not first:
            tk.Frame(self.inner, height=1, bg=C.BORDER).pack(fill="x", pady=(14, 0))
        tk.Label(self.inner, text=title, font=(FONT, 10, "bold"), fg=C.ACCENT2, bg=C.BG,
                 anchor="w").pack(fill="x", padx=22, pady=(14, 2))

    def row(self, title, sub=None, command=None, right=None):
        """right: None | "chevron" | callable(parent) -> widget"""
        cur = "hand2" if command else ""
        f = tk.Frame(self.inner, bg=C.BG, cursor=cur)
        f.pack(fill="x", padx=22, pady=7)
        widgets = [f]
        if right == "chevron":
            c = tk.Label(f, text="\u203a", font=(FONT, 18), fg=C.MUTED, bg=C.BG, cursor=cur)
            c.pack(side="right")
            widgets.append(c)
        elif callable(right):
            right(f).pack(side="right", padx=(8, 0))
        left = tk.Frame(f, bg=C.BG, cursor=cur)
        left.pack(side="left", fill="x", expand=True)
        widgets.append(left)
        t = tk.Label(left, text=title, font=(FONT, 12), fg=C.TEXT, bg=C.BG, anchor="w", cursor=cur)
        t.pack(fill="x")
        widgets.append(t)
        if sub:
            s = tk.Label(left, text=sub, font=(FONT, 10), fg=C.MUTED, bg=C.BG, anchor="w", justify="left",
                         wraplength=265, cursor=cur)
            s.pack(fill="x")
            widgets.append(s)
        if command:
            for w in widgets:
                w.bind("<Button-1>", lambda e: command(f))
        return f

    def toggle(self, title, sub, value, setter):
        holder = []

        def make(parent):
            sw = Switch(parent, value, setter, C.BG)
            holder.append(sw)
            return sw
        return self.row(title, sub, command=lambda f: holder[0]._click(), right=make)

    # ---- content
    def fill(self):
        a, S = self.app, self.app.settings
        self.section("Appearance", first=True)
        self.row("Theme", THEME_LABELS[S["theme"]], right="chevron",
                 command=lambda w: popup_choice(w, THEME_LABELS, S["theme"], a.set_theme_pref))

        self.section("Connection")
        self.toggle("Verify exit location", "Check that the tunnel exits in the selected country",
                    S["verify_exit"], lambda v: a.set_setting("verify_exit", v, "core"))

        self.section("DNS")
        self.row("Encrypted DNS", DNS_LABELS[S["dns_mode"]], right="chevron",
                 command=lambda w: popup_choice(w, DNS_LABELS, S["dns_mode"],
                                                lambda k: self._set_dns(k)))
        self.toggle("Use a custom DNS server",
                    S["custom_dns"] if (S["custom_dns_on"] and S["custom_dns"])
                    else "Send DNS lookups to a server you choose",
                    S["custom_dns_on"], self._custom_dns_toggled)
        if S["custom_dns_on"]:
            self.row("Custom DNS server", S["custom_dns"] or "Not set", right="chevron",
                     command=lambda w: self._edit("custom_dns", "Custom DNS server",
                                                  "IP address or https:// DoH URL (separate several with spaces).",
                                                  v_dns, "engine"))

        self.section("Local proxy")
        self.toggle("Proxy-only mode", "Run local proxy servers (SOCKS5 & HTTP) without a VPN interface",
                    not a.use_tun.get(), self._proxy_only_toggled)
        self.row("Local address", S["listen"], right="chevron",
                 command=lambda w: self._edit("listen", "Local address",
                                              "127.0.0.1 keeps the proxy private to this PC; 0.0.0.0 shares it "
                                              "with your network.", v_host, "core"))
        self.row("SOCKS5 port", a.port_var.get(), right="chevron", command=lambda w: self._edit_port())
        self.toggle("Enable HTTP proxy", "Run local HTTP proxy alongside SOCKS5", S["http_on"],
                    lambda v: self._http_toggled(v))
        if S["http_on"]:
            self.row("HTTP proxy port", str(S["http_port"]), right="chevron",
                     command=lambda w: self._edit("http_port", "HTTP proxy port",
                                                  "Applications that only support HTTP proxies use this port.",
                                                  v_port, "engine", cast=int))

        self.section("Split tunneling")
        self.row("Apps", a.split_summary().replace("\u203a", "").strip(), right="chevron",
                 command=lambda w: a.open_split())

        self.section("Advanced")
        self.row("Custom edge address", S["edge"] or "Not set", right="chevron",
                 command=lambda w: self._edit("edge", "Custom edge address",
                                              "Connect to this exact Mozilla edge (host:port) instead of a "
                                              "country. Leave empty to clear.", v_edge, "core"))
        self.toggle("Chain through upstream proxy",
                    "Connect to the VPN server through another proxy first"
                    + ("" if a.use_tun.get() else "  (needs Proxy-only mode off)"),
                    S["upstream_on"], self._upstream_toggled)
        if S["upstream_on"]:
            self.row("Upstream proxy", S["upstream"] or "Not set", right="chevron",
                     command=lambda w: self._edit("upstream", "Upstream proxy",
                                                  "socks5://host:port or http://host:port "
                                                  "(user:pass@ is allowed).", v_upstream, "engine"))
        self.row("Sign-in proxy", S["api_proxy"] or "Not set", right="chevron",
                 command=lambda w: self._edit("api_proxy", "Sign-in proxy",
                                              "Used only to reach Firefox Accounts if they are blocked "
                                              "(e.g. socks5://127.0.0.1:10808). Leave empty to clear.",
                                              v_api_proxy, "core"))

        self.section("About")
        self.row("View logs", "Recent connection activity", right="chevron",
                 command=lambda w: (a.close_settings(), a.show_log()))
        self.row("Version", a.VERSION)
        self.row("Source code", "Based on FoxyVPN by Vauth (MIT) - github.com/Vauth/FoxyVPN",
                 command=lambda w: webbrowser.open(SOURCE_URL), right="chevron")

        self.section("Account")
        email = a.state_data.get("email")
        self.row(email or "Manage account", "Subscription status and data usage", right="chevron",
                 command=lambda w: AccountDialog(a))
        b = button(self.inner, "\u21aa   Sign out", a.sign_out, danger=True)
        b.pack(fill="x", padx=22, pady=(14, 28), ipady=4)

    # ---- handlers
    def _set_dns(self, key):
        self.app.set_setting("dns_mode", key, "engine")
        self.refill()

    def _edit(self, key, title, label, validator, kind, cast=str):
        cur = self.app.settings[key]
        v = ask_text(self.app, title, label, str(cur) if cur not in (None, 0) else "", validator)
        if v is not None:
            self.app.set_setting(key, cast(v) if v != "" else ("" if cast is str else cur), kind)
            if key == "edge" and v:
                self.app._log("[settings] custom edge address overrides the country choice")
        self.refill()

    def _edit_port(self):
        v = ask_text(self.app, "SOCKS5 port", "Local port for the SOCKS5 proxy.", self.app.port_var.get(), v_port)
        if v is not None:
            self.app.set_port(v)
        self.refill()

    def _custom_dns_toggled(self, on):
        S = self.app.settings
        if on and not S["custom_dns"]:
            v = ask_text(self.app, "Custom DNS server", "IP address or https:// DoH URL (several allowed, "
                         "separated by spaces).", "", v_dns)
            if v is None:
                self.refill()
                return
            S["custom_dns"] = v
        self.app.set_setting("custom_dns_on", on, "engine")
        self.refill()

    def _proxy_only_toggled(self, on):
        self.app.set_proxy_only(on)
        self.refill()

    def _http_toggled(self, on):
        self.app.set_setting("http_on", on, "engine")
        self.refill()

    def _upstream_toggled(self, on):
        S = self.app.settings
        if on and not S["upstream"]:
            v = ask_text(self.app, "Upstream proxy", "socks5://host:port or http://host:port", "", v_upstream)
            if v is None:
                self.refill()
                return
            S["upstream"] = v
        self.app.set_setting("upstream_on", on, "engine")
        self.refill()


# -------------------------------------------------------------------- account
class AccountDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Account")
        self.configure(bg=C.BG)
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()
        st = app.state_data
        q = st.get("quota") or {}
        email = st.get("email") or "Signed in"
        tk.Label(self, text="Account", bg=C.BG, fg=C.TEXT, font=(FONT, 15, "bold")).pack(
            anchor="w", padx=22, pady=(18, 0))
        tk.Label(self, text=email, bg=C.BG, fg=C.ACCENT2, font=(FONT, 11)).pack(anchor="w", padx=22, pady=(0, 10))

        if q.get("subscribed") is None:
            plan = "Unknown (press Refresh)"
        elif q["subscribed"]:
            plan = "Subscribed"
        else:
            plan = "Free  \u2022  " + (usage.fmt_bytes(q.get("limit")) + " / month" if q.get("limit") else "limited")
        rows = [("Plan", plan),
                ("Data used", usage.fmt_bytes(q.get("used")) + (" of " + usage.fmt_bytes(q["limit"]) if q.get("limit") else "")
                 if q.get("used") is not None else "-"),
                ("Data left", usage.fmt_bytes(q.get("left")) if q.get("left") is not None else "-"),
                ("Resets", usage.fmt_reset(q.get("reset")).replace("resets ", "") or "-"),
                ("Updated", usage.fmt_ago(q.get("fetched_at")) or "-")]
        card = tk.Frame(self, bg=C.CARD, highlightthickness=1, highlightbackground=C.BORDER)
        card.pack(fill="x", padx=22)
        for i, (k, v) in enumerate(rows):
            r = tk.Frame(card, bg=C.CARD)
            r.pack(fill="x", padx=14, pady=(10 if i == 0 else 4, 10 if i == len(rows) - 1 else 4))
            tk.Label(r, text=k, bg=C.CARD, fg=C.MUTED, font=(FONT, 10)).pack(side="left")
            tk.Label(r, text=v, bg=C.CARD, fg=C.TEXT, font=(FONT, 10, "bold")).pack(side="right")

        row = tk.Frame(self, bg=C.BG)
        row.pack(fill="x", padx=22, pady=(14, 6))
        button(row, "Refresh", self._refresh).pack(side="left")
        button(row, "Firefox account page",
               lambda: webbrowser.open("https://accounts.firefox.com/settings")).pack(side="left", padx=8)
        button(self, "\u21aa   Sign out", self._sign_out, danger=True).pack(fill="x", padx=22, pady=(6, 20))

    def _refresh(self):
        self.app.refresh_usage(True)
        self.destroy()

    def _sign_out(self):
        self.destroy()
        self.app.sign_out()
