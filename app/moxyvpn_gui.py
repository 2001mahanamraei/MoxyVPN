"""MoxyVPN - Firefox VPN client: SOCKS5 proxy, whole-system tunnel, usage tracking, tray."""
import ctypes
import http.server
import importlib
import json
import math
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import settings_ui
import theme
import tunconf
import fx
import usage
import webbrowser
from theme import mix

APP_NAME = "MoxyVPN"
HOST = "127.0.0.1"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(APP_DIR, "assets")
TUN_DIR = os.path.join(os.path.dirname(APP_DIR), "tun")
MIHOMO = os.path.join(TUN_DIR, "mihomo.exe")
WINTUN = os.path.join(TUN_DIR, "wintun.dll")
TOKENS = os.path.join(os.path.expanduser("~"), ".foxyvpn-tokens.json")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
USAGE_REFRESH_SECONDS = 600
API_PORT = 47832

# ---- palette ---------------------------------------------------------------
BG = CARD = FIELD = BORDER = TEXT = MUTED = DIM = ACCENT = ACCENT2 = GREEN = RED = ""


def apply_palette(name):
    globals().update(theme.set_theme(name))


apply_palette("dark")
FONT = "Segoe UI"
VERSION = "1.3.0"
DEFAULT_SETTINGS = {
    "theme": "dark", "verify_exit": True, "dns_mode": "auto", "custom_dns_on": False, "custom_dns": "",
    "listen": "127.0.0.1", "fx_on": True, "http_on": False, "http_port": 8080, "edge": "", "upstream_on": False,
    "upstream": "", "api_proxy": "",
}

COUNTRIES = [
    ("Auto (suggested)", ""), ("United States", "us"), ("Canada", "ca"), ("United Kingdom", "gb"),
    ("Germany", "de"), ("France", "fr"), ("Netherlands", "nl"), ("Sweden", "se"),
    ("Switzerland", "ch"), ("Spain", "es"), ("Italy", "it"), ("Japan", "jp"),
    ("Singapore", "sg"), ("Australia", "au"),
]
W, H = 400, 758


def rrect(c, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
           x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


HERO_N = 60   # number of ticks around the power button
LOG_W = 36    # side log panel width (chars)


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _rgb(t):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in t)


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def python_exe():
    exe = sys.executable
    if os.path.basename(exe).lower() == "pythonw.exe":
        alt = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.exists(alt):
            return alt
    return exe


def ensure_tray_deps():
    def ok():
        try:
            importlib.invalidate_caches()
            importlib.import_module("pystray")
            importlib.import_module("PIL.Image")
            return True
        except Exception:
            return False
    return ok()


class _ApiHandler(http.server.BaseHTTPRequestHandler):
    """Tiny local control API for the MoxyVPN Chrome extension (127.0.0.1 only)."""
    app = None

    def log_message(self, *args):
        pass

    def _host_ok(self):
        return self.headers.get("Host", "") in (f"127.0.0.1:{API_PORT}", f"localhost:{API_PORT}")

    def _origin(self):
        o = self.headers.get("Origin", "")
        return o if o.startswith("chrome-extension://") else ""

    def _send(self, code, obj=None):
        body = json.dumps(obj if obj is not None else {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if self._origin():
            self.send_header("Access-Control-Allow-Origin", self._origin())
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if not (self._host_ok() and self._origin()):
            return self._send(403, {"error": "forbidden"})
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self._origin())
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", "X-Moxy-Client")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "forbidden"})
        if self.path.split("?")[0] == "/status":
            return self._send(200, self.app.api_status())
        self._send(404, {"error": "not found"})

    def do_POST(self):
        # Only the extension may control the app: browsers always send Origin on POST.
        if not (self._host_ok() and self._origin() and self.headers.get("X-Moxy-Client") == "1"):
            return self._send(403, {"error": "forbidden"})
        actions = {"/connect": self.app.start, "/disconnect": self.app.stop,
                   "/refresh": self.app.refresh_usage}
        fn = actions.get(self.path.split("?")[0])
        if not fn:
            return self._send(404, {"error": "not found"})
        self.app.ui(fn)
        self._send(200, {"ok": True})


HIDE_PROCS = {"system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe",
              "services.exe", "lsass.exe", "svchost.exe", "fontdrvhost.exe", "dwm.exe",
              "conhost.exe", "winlogon.exe", "python.exe", "pythonw.exe", "mihomo.exe",
              "moxyvpn.exe", "tasklist.exe", "memory compression", "secure system"}


def running_processes():
    try:
        out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True,
                             creationflags=NO_WINDOW, timeout=10).stdout
    except Exception:
        return []
    names = set()
    for line in out.splitlines():
        first = line.split('","')[0].strip('"').strip()
        if first and first.lower() not in HIDE_PROCS:
            names.add(first)
    return sorted(names, key=str.lower)


def _dark_button(parent, text, cmd, accent=False):
    return tk.Button(parent, text=text, command=cmd, relief="flat", bd=0, cursor="hand2",
                     bg=ACCENT if accent else BORDER, fg="#1B0F05" if accent else TEXT,
                     activebackground=ACCENT2 if accent else mix(BORDER, TEXT, 0.12),
                     activeforeground="#1B0F05" if accent else TEXT,
                     font=(FONT, 10, "bold" if accent else "normal"), padx=12, pady=6)


class ProcessPicker(tk.Toplevel):
    """Pick one or more running programs."""

    def __init__(self, parent, on_add):
        super().__init__(parent)
        self.on_add = on_add
        self.title("Running apps")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.all = running_processes()
        tk.Label(self, text="Pick the apps to add", bg=BG, fg=TEXT, font=(FONT, 12, "bold")).pack(
            anchor="w", padx=18, pady=(16, 6))
        self.q = tk.StringVar()
        e = tk.Entry(self, textvariable=self.q, bg=CARD, fg=TEXT, insertbackground=TEXT, relief="flat",
                     font=(FONT, 10), highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=ACCENT)
        e.pack(fill="x", padx=18, ipady=5)
        e.focus_set()
        self.q.trace_add("write", lambda *a: self._fill())
        box = tk.Frame(self, bg=BG)
        box.pack(fill="both", padx=18, pady=8)
        self.lb = tk.Listbox(box, selectmode="extended", height=12, width=34, bg=CARD, fg=TEXT,
                             selectbackground=ACCENT, selectforeground="#1B0F05", relief="flat",
                             highlightthickness=0, font=(FONT, 10), activestyle="none")
        sb = tk.Scrollbar(box, command=self.lb.yview)
        self.lb.config(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=18, pady=(0, 16))
        _dark_button(row, "Add selected", self._add, True).pack(side="right")
        _dark_button(row, "Cancel", self.destroy).pack(side="right", padx=8)
        self._fill()

    def _fill(self):
        t = self.q.get().strip().lower()
        self.lb.delete(0, "end")
        for n in self.all:
            if t in n.lower():
                self.lb.insert("end", n)

    def _add(self):
        self.on_add([self.lb.get(i) for i in self.lb.curselection()])
        self.destroy()


class SplitDialog(tk.Toplevel):
    MODES = (("off", "Off"), ("exclude", "Bypass selected apps"), ("include", "Only selected apps"))
    HELP = {
        "off": "Everything goes through the VPN.",
        "exclude": "Selected apps skip the VPN and use your normal connection. Everything else is protected.",
        "include": "Only the selected apps use the VPN. Everything else uses your normal connection.",
    }

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Split tunneling")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()
        self.mode = tk.StringVar(value=app.split["mode"])
        self.apps = list(app.split["apps"])

        tk.Label(self, text="Split tunneling", bg=BG, fg=TEXT, font=(FONT, 15, "bold")).pack(
            anchor="w", padx=20, pady=(18, 2))
        tk.Label(self, text="Choose which programs use the VPN.", bg=BG, fg=MUTED,
                 font=(FONT, 10)).pack(anchor="w", padx=20)

        seg = tk.Frame(self, bg=CARD)
        seg.pack(fill="x", padx=20, pady=(14, 6))
        self.radios = {}
        for val, label in self.MODES:
            rb = tk.Radiobutton(seg, text=label, value=val, variable=self.mode, indicatoron=False,
                                command=self._mode_changed, bg=CARD, fg=MUTED, selectcolor=ACCENT,
                                activebackground=BORDER, activeforeground=TEXT, relief="flat", bd=0,
                                font=(FONT, 9, "bold"), padx=6, pady=7, cursor="hand2")
            rb.pack(side="left", fill="x", expand=True, padx=2, pady=2)
            self.radios[val] = rb
        self.help = tk.Label(self, text="", bg=BG, fg=MUTED, font=(FONT, 9), wraplength=340,
                             justify="left")
        self.help.pack(anchor="w", padx=20, pady=(0, 8))

        box = tk.Frame(self, bg=BG)
        box.pack(fill="both", padx=20)
        self.lb = tk.Listbox(box, selectmode="extended", height=9, width=38, bg=CARD, fg=TEXT,
                             selectbackground=ACCENT, selectforeground="#1B0F05", relief="flat",
                             highlightthickness=0, font=(FONT, 10), activestyle="none")
        sb = tk.Scrollbar(box, command=self.lb.yview)
        self.lb.config(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=20, pady=8)
        _dark_button(row, "Add running app", self._add_running).pack(side="left")
        _dark_button(row, "Browse .exe", self._browse).pack(side="left", padx=6)
        _dark_button(row, "Remove", self._remove).pack(side="right")

        self.note = tk.Label(self, text="", bg=BG, fg=ACCENT2, font=(FONT, 9), wraplength=340,
                             justify="left")
        self.note.pack(anchor="w", padx=20)
        if not app.use_tun.get():
            self.note.config(text="Turn on \u201cTunnel whole system\u201d to use split tunneling.")

        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=20, pady=16)
        _dark_button(foot, "Save", self._save, True).pack(side="right")
        _dark_button(foot, "Cancel", self.destroy).pack(side="right", padx=8)
        self._refresh()
        self._mode_changed()

    def _refresh(self):
        self.lb.delete(0, "end")
        for a in self.apps:
            self.lb.insert("end", a)

    def _mode_changed(self):
        self.help.config(text=self.HELP[self.mode.get()])
        for val, rb in self.radios.items():
            sel = val == self.mode.get()
            rb.config(fg="#1B0F05" if sel else MUTED, activeforeground="#1B0F05" if sel else TEXT)

    def _add_names(self, names):
        have = {a.lower() for a in self.apps}
        for n in names:
            n = n.strip()
            if n and "," not in n and n.lower() not in have:
                self.apps.append(n)
                have.add(n.lower())
        if self.mode.get() == "off" and self.apps:
            self.mode.set("exclude")
            self._mode_changed()
        self._refresh()

    def _add_running(self):
        ProcessPicker(self, self._add_names)

    def _browse(self):
        path = filedialog.askopenfilename(parent=self, title="Choose a program",
                                          filetypes=[("Programs", "*.exe"), ("All files", "*.*")])
        if path:
            self._add_names([os.path.basename(path)])

    def _remove(self):
        for i in reversed(self.lb.curselection()):
            del self.apps[i]
        self._refresh()

    def _save(self):
        self.app.set_split(self.mode.get(), self.apps)
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.state_data = usage.load_state()
        self.settings = {**DEFAULT_SETTINGS, **(self.state_data.get("settings") or {})}
        if not self.settings["api_proxy"]:
            self.settings["api_proxy"] = self.state_data.get("api_proxy", "")
        apply_palette(self.settings["theme"])
        self.VERSION = VERSION
        self.settings_page = None
        self.settings_open = False
        self.log_lines = []
        self._pending_email = None
        self.title(APP_NAME)
        self.configure(bg=BG)
        self.resizable(False, False)
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MoxyVPN.App")
        except Exception:
            pass
        try:
            self._icon_img = tk.PhotoImage(file=os.path.join(ASSETS, "moxy_64.png"))
            self.iconphoto(True, self._icon_img)
        except tk.TclError:
            pass

        self.proc = None
        self.tun = None
        self.q = queue.Queue()
        self.vstate = "off"
        self.spin_angle = 0
        self.tray = None
        self.tray_imgs = None
        self.notified = False
        self.fetching = False
        self.last_fetch = 0
        self.log_visible = False
        self.login_ctx = None
        self.login_busy = False
        self.need_login = False
        self.api_port_cache = 1080
        self.api = None

        self.port_var = tk.StringVar(value=str(self.state_data.get("port", "1080")))
        self.use_tun = tk.BooleanVar(value=("--tun" in sys.argv) or bool(self.state_data.get("tun")))
        code = self.state_data.get("country", "us")
        self.country_code = code
        self.country_text = tk.StringVar(value=self._country_label(code))
        sp = self.state_data.get("split") or {}
        self.split = {"mode": sp.get("mode", "off"), "apps": list(sp.get("apps", []))}
        self.api_proxy_var = tk.StringVar(value=self.settings["api_proxy"])
        try:
            self.api_port_cache = int(self.port_var.get())
        except ValueError:
            pass

        self._build()
        self._build_login()
        self._start_api()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.fx = fx.FX(self, self.c, ASSETS)
        self.set_state("off")
        self.render_usage()
        self.update_split_chip()
        self.after(100, self._tick)
        self.after(40, self._anim)
        threading.Thread(target=self._tray_thread, daemon=True).start()
        if os.path.exists(TOKENS):
            self.after(1500, self.refresh_usage)
            if "--auto" in sys.argv:
                self.after(500, self.start)
        else:
            self.show_login()

    # ------------------------------------------------------------------ UI
    def _country_label(self, code):
        for name, c in COUNTRIES:
            if c == code:
                return name + "  \u25be"
        return code.upper() + "  \u25be"

    def _build(self):
        c = self.c = tk.Canvas(self, width=W, height=H, bg=BG, highlightthickness=0)
        c.pack(side="left")
        self._bg_img = self._make_bg()
        c.create_image(0, 0, image=self._bg_img, anchor="nw")

        # header
        try:
            self._logo = tk.PhotoImage(file=os.path.join(ASSETS, "moxy_40.png"))
            c.create_image(22, 38, image=self._logo, anchor="w")
        except tk.TclError:
            pass
        c.create_text(72, 30, text="MoxyVPN", anchor="w", fill=TEXT, font=(FONT, 17, "bold"))
        self.hdr_sub = c.create_text(73, 52, text=self._email_text(), anchor="w", fill=MUTED,
                                     font=(FONT, 9))
        dark = theme.resolve(self.settings["theme"]) == "dark"
        c.create_rectangle(296, 20, 340, 56, fill=self._bg_hex(318, 38), outline="", tags="theme")
        c.create_text(318, 38, text="\u2600" if dark else "\u263e", fill=ACCENT2 if dark else TEXT,
                      font=("Segoe UI Symbol", 16), tags="theme")
        c.create_rectangle(346, 20, 388, 56, fill=self._bg_hex(366, 38), outline="", tags="menu")
        for dy in (-6, 0, 6):
            c.create_line(354, 38 + dy, 376, 38 + dy, fill=TEXT, width=2, capstyle="round", tags="menu")
        c.tag_bind("theme", "<Button-1>", lambda e: self.toggle_theme())
        c.tag_bind("menu", "<Button-1>", lambda e: self.open_settings())

        # hero power button
        cx, cy, R = 200, 190, 62
        self.hero_c = (cx, cy)
        self.glow = [c.create_oval(cx - r, cy - r, cx + r, cy + r, fill="", outline=BG,
                                   width=7, tags="hero") for r in (R + 49, R + 42, R + 35, R + 28)]
        self.ticks = []
        for i in range(HERO_N):
            a = math.radians(i * 360 / HERO_N - 90)
            r1, r2 = R + 14, R + (25 if i % 5 == 0 else 20)
            self.ticks.append(c.create_line(
                cx + r1 * math.cos(a), cy + r1 * math.sin(a),
                cx + r2 * math.cos(a), cy + r2 * math.sin(a),
                width=3 if i % 5 == 0 else 2, fill=BORDER, capstyle="round", tags="hero"))
        self.ring = c.create_oval(cx - R, cy - R, cx + R, cy + R, fill=CARD, outline=BORDER,
                                  width=5, tags="hero")
        self.face = []
        for i in range(7):
            r = R - 8 - i * 6
            self.face.append(c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=CARD,
                                           outline="", tags="hero"))
        c.create_arc(cx - R + 9, cy - R + 9, cx + R - 9, cy + R - 9, start=105, extent=60,
                     style="arc", width=3, outline=mix(CARD, "#FFFFFF", 0.22), tags="hero")
        self.spin = c.create_arc(cx - R, cy - R, cx + R, cy + R, start=0, extent=70, style="arc",
                                 width=5, outline=ACCENT, state="hidden", tags="hero")
        self.spin2 = c.create_arc(cx - R, cy - R, cx + R, cy + R, start=80, extent=60, style="arc",
                                  width=5, outline=mix(CARD, ACCENT, 0.5), state="hidden", tags="hero")
        self.spin3 = c.create_arc(cx - R, cy - R, cx + R, cy + R, start=140, extent=50, style="arc",
                                  width=5, outline=mix(CARD, ACCENT, 0.22), state="hidden", tags="hero")
        self.p_arc_g = c.create_arc(cx - 26, cy - 22, cx + 26, cy + 30, start=125, extent=290,
                                    style="arc", width=12, outline=CARD, tags="hero")
        self.p_line_g = c.create_line(cx, cy - 36, cx, cy - 8, width=12, fill=CARD,
                                      capstyle="round", tags="hero")
        self.p_arc = c.create_arc(cx - 26, cy - 22, cx + 26, cy + 30, start=125, extent=290,
                                  style="arc", width=6, outline=DIM, tags="hero")
        self.p_line = c.create_line(cx, cy - 34, cx, cy - 8, width=6, fill=DIM,
                                    capstyle="round", tags="hero")
        c.tag_bind("hero", "<Button-1>", lambda e: self.toggle())
        for tag in ("hero", "copy", "tun", "refresh", "logt", "theme", "menu"):
            c.tag_bind(tag, "<Enter>", lambda e: c.config(cursor="hand2"))
            c.tag_bind(tag, "<Leave>", lambda e: c.config(cursor=""))
        self.s_title = c.create_text(200, 303, text="", fill=TEXT, font=(FONT, 17, "bold"))
        self.s_sub = c.create_text(200, 328, text="", fill=MUTED, font=(FONT, 10))

        # connection card
        rrect(c, 20, 352, 380, 538, 16, fill=CARD, outline=mix(BORDER, ACCENT, 0.25))
        for y in (399, 445, 491):
            c.create_line(38, y, 362, y, fill=BORDER)
        c.create_text(38, 375, text="SOCKS5 proxy", anchor="w", fill=MUTED, font=(FONT, 10))
        self.addr_item = c.create_text(150, 375, text=self.listen_host() + " :", anchor="w", fill=TEXT,
                                       font=("Consolas", 11))
        self.port_entry = tk.Entry(self, textvariable=self.port_var, width=6, justify="center",
                                   bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat",
                                   font=("Consolas", 11), highlightthickness=1,
                                   highlightbackground=BORDER, highlightcolor=ACCENT,
                                   disabledbackground=FIELD, disabledforeground=DIM)
        c.create_window(280, 375, window=self.port_entry, width=50, height=26)
        rrect(c, 322, 363, 362, 387, 8, fill=BORDER, tags="copy")
        c.create_text(342, 375, text="Copy", fill=TEXT, font=(FONT, 9), tags="copy")
        c.tag_bind("copy", "<Button-1>", lambda e: self.copy_addr())

        c.create_text(38, 422, text="Country", anchor="w", fill=MUTED, font=(FONT, 10))
        self.mb = tk.Menubutton(self, textvariable=self.country_text, bg=BORDER, fg=TEXT,
                                activebackground=mix(BORDER, TEXT, 0.12), activeforeground=TEXT,
                                relief="flat", bd=0, padx=12, pady=3, font=(FONT, 10),
                                disabledforeground=DIM)
        menu = tk.Menu(self.mb, tearoff=0, bg=CARD, fg=TEXT, activebackground=ACCENT,
                       activeforeground="#1B0F05", bd=0, font=(FONT, 10))
        for name, code in COUNTRIES:
            menu.add_command(label=name, command=lambda n=name, k=code: self.pick_country(n, k))
        self.mb["menu"] = menu
        c.create_window(362, 422, window=self.mb, anchor="e")

        c.create_text(38, 468, text="Tunnel whole system", anchor="w", fill=MUTED, font=(FONT, 10))
        self.t_track = rrect(c, 318, 458, 362, 478, 10, fill=BORDER, tags="tun")
        self.t_knob = c.create_oval(320, 460, 340, 476, fill=TEXT, outline="", tags="tun")
        c.tag_bind("tun", "<Button-1>", lambda e: self.flip_tun())
        self.draw_toggle()

        c.create_text(38, 514, text="Split tunneling", anchor="w", fill=MUTED, font=(FONT, 10))
        rrect(c, 232, 502, 362, 526, 8, fill=BORDER, tags="split")
        self.split_txt = c.create_text(297, 514, text="", fill=TEXT, font=(FONT, 9), tags="split")
        c.tag_bind("split", "<Button-1>", lambda e: self.open_split())
        c.tag_bind("split", "<Enter>", lambda e: c.config(cursor="hand2"))
        c.tag_bind("split", "<Leave>", lambda e: c.config(cursor=""))

        # usage card
        rrect(c, 20, 558, 380, 718, 16, fill=CARD, outline=mix(BORDER, ACCENT, 0.25))
        c.create_text(38, 580, text="DATA USAGE", anchor="w", fill=MUTED, font=(FONT, 8, "bold"))
        c.create_text(362, 580, text="\u21bb  Refresh", anchor="e", fill=ACCENT2, font=(FONT, 9),
                      tags="refresh")
        c.tag_bind("refresh", "<Button-1>", lambda e: self.refresh_usage(True))
        self.u_used = c.create_text(38, 622, text="-", anchor="w", fill=TEXT, font=(FONT, 28, "bold"))
        self.u_of = c.create_text(362, 632, text="", anchor="e", fill=MUTED, font=(FONT, 11))
        rrect(c, 38, 658, 362, 668, 5, fill=BORDER)
        self.u_bar = None
        self.u_line = c.create_text(38, 688, text="", anchor="w", fill=MUTED, font=(FONT, 9))
        self.u_upd = c.create_text(38, 706, text="", anchor="w", fill=DIM, font=(FONT, 8))

        # log toggle (side panel)
        self.logt = c.create_text(200, H - 20, text="Show log  \u25b8", fill=DIM, font=(FONT, 9),
                                  tags="logt")
        c.tag_bind("logt", "<Button-1>", lambda e: self.toggle_log())
        self.log_frame = tk.Frame(self, bg=CARD)
        tk.Frame(self.log_frame, bg=BORDER, width=1).pack(side="left", fill="y")
        head = tk.Frame(self.log_frame, bg=CARD)
        head.pack(side="top", fill="x", padx=12, pady=(14, 6))
        tk.Label(head, text="LOG", bg=CARD, fg=MUTED, font=(FONT, 8, "bold")).pack(side="left")
        clr = tk.Label(head, text="Clear", bg=CARD, fg=ACCENT2, font=(FONT, 9), cursor="hand2")
        clr.pack(side="right")
        clr.bind("<Button-1>", lambda e: self._clear_log())
        self.log = tk.Text(self.log_frame, width=LOG_W, height=1, bg=CARD, fg=MUTED, relief="flat",
                           font=("Consolas", 9), state="disabled", highlightthickness=0, wrap="word")
        self.log.pack(side="top", fill="both", expand=True, padx=(12, 10), pady=(0, 12))

    # ---- background ----
    def _make_bg(self):
        SC = 4
        self._bgp = (_hex(BG), _hex(mix(BG, ACCENT, 0.16)), _hex(ACCENT))
        w, h = W // SC, (H + SC - 1) // SC
        img = tk.PhotoImage(width=w, height=h)
        for y in range(h):
            row = [_rgb(self._bg_rgb(x * SC + SC / 2, y * SC + SC / 2)) for x in range(w)]
            img.put("{" + " ".join(row) + "}", to=(0, y))
        return img.zoom(SC)

    def _bg_rgb(self, x, y):
        top, bot, tint = self._bgp
        t = min(max(y / (H - 1), 0.0), 1.0)
        k = max(0.0, 1 - math.hypot(x - 200, y - 190) / 190) ** 2 * 0.16
        out = []
        for a, b, tc in zip(top, bot, tint):
            base = a + (b - a) * t
            out.append(base + (tc - base) * k)
        return tuple(out)

    def _bg_hex(self, x, y):
        return _rgb(self._bg_rgb(x, y))

    def draw_toggle(self):
        on = self.use_tun.get()
        busy = self.proc is not None
        col = (ACCENT if on else BORDER)
        if busy:
            col = mix(col, BG, 0.45)
        self.c.itemconfig(self.t_track, fill=col)
        x = 342 if on else 320
        self.c.coords(self.t_knob, x, 460, x + 20, 476)
        self.c.itemconfig(self.t_knob, fill="#FFFFFF" if not busy else mix("#FFFFFF", BG, 0.45))

    def flip_tun(self):
        if self.proc:
            return
        self.use_tun.set(not self.use_tun.get())
        self.draw_toggle()

    def pick_country(self, name, code):
        self.country_code = code
        self.country_text.set(name + "  \u25be")

    def copy_addr(self):
        self.clipboard_clear()
        self.clipboard_append(f"{self.listen_display()}:{self.port_var.get().strip()}")
        self.c.itemconfig(self.s_sub, text="Address copied")
        self.after(1200, self._refresh_sub)

    def toggle_log(self):
        self.log_visible = not self.log_visible
        if self.log_visible:
            self.log_frame.pack(side="right", fill="y")
        else:
            self.log_frame.pack_forget()
        self.c.itemconfig(self.logt, text="Hide log  \u25c2" if self.log_visible else "Show log  \u25b8")
        self.geometry("")

    def _clear_log(self):
        self.log_lines.clear()
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    def _log(self, text):
        self.log_lines.append(text)
        del self.log_lines[:-400]
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # ------------------------------------------------------------ appearance
    def set_state(self, vs):
        prev = getattr(self, "vstate", None)
        self.vstate = vs
        if prev is not None and prev != vs and hasattr(self, "fx"):
            self.fx.enabled = bool(self.settings.get("fx_on", True))
            if prev == "off" and vs == "connecting":
                self.fx.play("connect")
            elif vs == "off":
                self.fx.play("disconnect")
        c = self.c
        pal = {
            "off": (BORDER, None, DIM, "Disconnected", TEXT),
            "connecting": (mix(CARD, ACCENT, 0.5), ACCENT, ACCENT2, "Connecting...", TEXT),
            "on": (GREEN, GREEN, GREEN, "Protected", GREEN),
        }[vs]
        ring, glow, icon, title, tcol = pal
        bgc = self._bg_hex(*self.hero_c)
        self.tick_off = mix(bgc, BORDER, 0.9)
        c.itemconfig(self.ring, outline=ring)
        n = len(self.glow)
        for i, item in enumerate(self.glow):
            t = 0.05 + 0.13 * (i + 1) / n
            c.itemconfig(item, outline=mix(bgc, glow, t) if glow else bgc)
        fc = CARD
        for i, item in enumerate(self.face):
            fc = mix(CARD, glow, 0.04 * (i + 1)) if glow else mix(CARD, TEXT, 0.012 * (i + 1))
            c.itemconfig(item, fill=fc)
        c.itemconfig(self.p_arc, outline=icon)
        c.itemconfig(self.p_line, fill=icon)
        gcol = mix(fc, icon, 0.30) if glow else fc
        c.itemconfig(self.p_arc_g, outline=gcol)
        c.itemconfig(self.p_line_g, fill=gcol)
        for sp in (self.spin, self.spin2, self.spin3):
            c.itemconfig(sp, state="normal" if vs == "connecting" else "hidden")
        if vs == "off":
            for t_ in self.ticks:
                c.itemconfig(t_, fill=self.tick_off)
        c.itemconfig(self.s_title, text=title, fill=tcol)
        self._refresh_sub()
        busy = self.proc is not None
        self.port_entry.config(state="disabled" if busy else "normal")
        self.mb.config(state="disabled" if busy else "normal")
        self.draw_toggle()
        self.update_tray()

    def _refresh_sub(self):
        if self.vstate == "off":
            txt = "Tap the power button to connect"
        elif self.vstate == "connecting":
            txt = "Signing in and picking a server"
        else:
            txt = f"socks5://{self.listen_display()}:{self.port_var.get().strip()}"
            if self.tun and self.use_tun.get():
                txt += "  \u2022  whole system"
            if self.settings["http_on"] and self.tun:
                txt += f"  \u2022  http :{self.settings['http_port']}"
        self.c.itemconfig(self.s_sub, text=txt)

    def _anim(self):
        c, now = self.c, time.time()
        if self.vstate == "connecting":
            self.spin_angle = (self.spin_angle - 16) % 360
            a = self.spin_angle
            c.itemconfig(self.spin, start=a)
            c.itemconfig(self.spin2, start=a + 80)
            c.itemconfig(self.spin3, start=a + 140)
            head = int(now * 28) % HERO_N
            for i, t_ in enumerate(self.ticks):
                k = max(0.0, 1 - ((head - i) % HERO_N) / 16)
                c.itemconfig(t_, fill=mix(self.tick_off, ACCENT2, k))
        elif self.vstate == "on":
            t = 0.5 + 0.5 * math.sin(now * 2)
            bgc = self._bg_hex(*self.hero_c)
            n = len(self.glow)
            for i, item in enumerate(self.glow):
                c.itemconfig(item, outline=mix(bgc, GREEN, (0.05 + 0.13 * (i + 1) / n) * (0.7 + 0.3 * t)))
            for i, t_ in enumerate(self.ticks):
                w = 0.5 + 0.5 * math.sin(now * 2.4 - i * 0.314)
                c.itemconfig(t_, fill=mix(self.tick_off, GREEN, 0.2 + 0.8 * w))
        self.after(40, self._anim)

    # ----------------------------------------------------------------- usage
    def render_usage(self):
        q = self.state_data.get("quota") or {}
        used, limit, left, reset = q.get("used"), q.get("limit"), q.get("left"), q.get("reset")
        c = self.c
        c.itemconfig(self.u_used, text=usage.fmt_bytes(used) if used is not None else "-")
        c.itemconfig(self.u_of, text=f"of {usage.fmt_bytes(limit)}" if limit else "")
        if self.u_bar:
            c.delete(self.u_bar)
            self.u_bar = None
        frac = 0.0
        if used is not None and limit:
            frac = min(max(used / limit, 0.0), 1.0)
        if frac > 0:
            x2 = 38 + max(324 * frac, 10)
            self.u_bar = rrect(c, 38, 658, x2, 668, 5, fill=RED if frac >= 0.9 else ACCENT)
        parts = []
        if left is not None:
            parts.append(f"{usage.fmt_bytes(left)} left")
        if reset:
            if reset < time.time() and q.get("fetched_at", 0) < reset:
                parts.append("new cycle started - refresh")
            else:
                parts.append(usage.fmt_reset(reset))
        if not parts:
            parts.append("Tap Refresh to read your usage" if os.path.exists(TOKENS) else "Sign in first")
        c.itemconfig(self.u_line, text="  \u2022  ".join(parts))
        ago = usage.fmt_ago(q.get("fetched_at"))
        c.itemconfig(self.u_upd, text=f"Updated {ago}" if ago else "")
        self.update_header()
        self.update_tray()

    def usage_text(self):
        q = self.state_data.get("quota") or {}
        if q.get("used") is None:
            return "Usage: not read yet"
        return f"Used {usage.fmt_bytes(q['used'])} of {usage.fmt_bytes(q.get('limit'))}"

    def refresh_usage(self, manual=False):
        if self.fetching:
            return
        if not os.path.exists(TOKENS):
            if manual:
                messagebox.showinfo(APP_NAME, "Sign in first (press Connect, or run First login).")
            return
        self.fetching = True
        self.c.itemconfig(self.u_upd, text="Updating...")

        def work():
            try:
                self.q.put(("usage", usage.fetch_quota(self.api_proxy_var.get().strip() or None)))
            except Exception as exc:  # noqa: BLE001
                self.q.put(("usage_err", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ tray
    def ui(self, fn):
        self.q.put(("ui", fn))

    def _tray_thread(self):
        if not ensure_tray_deps():
            self.q.put(("log", "[tray] could not install pystray/Pillow - running without tray"))
            return
        try:
            import pystray
            from PIL import Image
            on_img = Image.open(os.path.join(ASSETS, "moxy_256.png")).convert("RGBA")
            gray = Image.merge("LA", (on_img.convert("L"), on_img.split()[3])).convert("RGBA")
            self.tray_imgs = (gray, on_img)
            menu = pystray.Menu(
                pystray.MenuItem("Open MoxyVPN", lambda i, it: self.ui(self.show), default=True),
                pystray.MenuItem(lambda it: "Disconnect" if self.proc else "Connect",
                                 lambda i, it: self.ui(self.toggle)),
                pystray.MenuItem(lambda it: self.usage_text(), None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", lambda i, it: self.ui(self.quit_app)),
            )
            self.tray = pystray.Icon(APP_NAME, gray, APP_NAME, menu)
            self.tray.run_detached()
            self.q.put(("ui", self.update_tray))
        except Exception as exc:  # noqa: BLE001
            self.q.put(("log", f"[tray] disabled: {exc}"))

    def update_tray(self):
        if not self.tray or not self.tray_imgs:
            return
        try:
            on = self.vstate == "on"
            self.tray.icon = self.tray_imgs[1 if self.vstate != "off" else 0]
            status = {"off": "Disconnected", "connecting": "Connecting...", "on": "Protected"}[self.vstate]
            self.tray.title = f"{APP_NAME} - {status}\n{self.usage_text()}"[:127]
            self.tray.update_menu()
        except Exception:
            pass

    def show(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def on_close(self):
        if self.tray:
            self.withdraw()
            if not self.notified:
                self.notified = True
                try:
                    self.tray.notify("MoxyVPN is still running here. Right-click to quit.", APP_NAME)
                except Exception:
                    pass
        else:
            self.quit_app()

    def quit_app(self):
        self.stop()
        if self.api:
            try:
                threading.Thread(target=self.api.shutdown, daemon=True).start()
            except Exception:
                pass
        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
        self.destroy()

    # ------------------------------------------------------------ connection
    def toggle(self):
        self.stop() if self.proc else self.start()

    def start(self):
        if self.proc:
            return
        if not os.path.exists(TOKENS):
            self.show_login()
            return
        port = self.port_var.get().strip()
        if not port.isdigit() or not 1 <= int(port) <= 65535:
            self.show()
            messagebox.showerror("Port", "Port must be a number between 1 and 65535.")
            return
        if self.use_tun.get() and not is_admin():
            self.show()
            messagebox.showerror("Administrator needed", "Open MoxyVPN.exe (it asks for Administrator) "
                                 "or turn on Proxy-only mode in Settings.")
            return
        if self.engine_needed():
            missing = not os.path.exists(MIHOMO) or (self.use_tun.get() and not os.path.exists(WINTUN))
            if missing:
                self.show()
                messagebox.showerror("Missing files", "tun\\mihomo.exe or tun\\wintun.dll not found.")
                return
        cmd = [python_exe(), "-m", "foxyvpn", "--listen", f"{self.listen_host()}:{port}"]
        if self.settings["edge"]:
            cmd += ["--proxy", self.settings["edge"]]
        elif self.country_code:
            cmd += ["--country", self.country_code]
        if not self.settings["verify_exit"]:
            cmd.append("--no-verify-exit")
        proxy = self.settings["api_proxy"].strip()
        if proxy:
            cmd += ["--api-proxy", proxy]
        self.need_login = False
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        try:
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=env, creationflags=NO_WINDOW, text=True, encoding="utf-8", errors="replace")
        except OSError as exc:
            self.show()
            messagebox.showerror("Error", str(exc))
            return
        self.api_port_cache = int(port)
        self.state_data.update(port=port, country=self.country_code, tun=self.use_tun.get())
        usage.save_state(self.state_data)
        threading.Thread(target=self._reader, args=("proxy", self.proc), daemon=True).start()
        self.set_state("connecting")

    def stop(self):
        self.stop_tun()
        if self.proc:
            p, self.proc = self.proc, None
            try:
                p.terminate()
            except OSError:
                pass
        self.set_state("off")

    def start_tun(self):
        if self.tun:
            return
        paths = {python_exe(), sys.executable}
        cfg = os.path.join(TUN_DIR, "config.yaml")
        with open(cfg, "w", encoding="utf-8") as f:
            S = self.settings
            lan = S["listen"] in ("0.0.0.0", "::")
            opts = {
                "tun": self.use_tun.get(), "lan": lan,
                "http_port": int(S["http_port"]) if S["http_on"] else 0,
                "socks_host": "127.0.0.1" if lan or S["listen"] in ("", "localhost") else S["listen"],
                "dns_mode": S["dns_mode"], "custom_dns_on": S["custom_dns_on"],
                "custom_dns": S["custom_dns"], "upstream": S["upstream"] if S["upstream_on"] else "",
            }
            f.write(tunconf.build(self.port_var.get().strip(), sorted(paths),
                                  self.split["mode"], self.split["apps"], opts))
        try:
            self.tun = subprocess.Popen(
                [MIHOMO, "-d", TUN_DIR, "-f", cfg], cwd=TUN_DIR, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=NO_WINDOW,
                text=True, encoding="utf-8", errors="replace")
        except OSError as exc:
            self._log(f"[tun] failed to start: {exc}")
            return
        threading.Thread(target=self._reader, args=("tun", self.tun), daemon=True).start()

    def stop_tun(self):
        if self.tun:
            p, self.tun = self.tun, None
            try:
                p.terminate()
                p.wait(timeout=3)
            except Exception:
                pass

    # --------------------------------------------------------------- sign in
    def _build_login(self):
        f = self.login_frame = tk.Frame(self, bg=BG)

        def entry(show=None, var=None):
            return tk.Entry(f, show=show, textvariable=var, bg=CARD, fg=TEXT, insertbackground=TEXT,
                            relief="flat", font=(FONT, 11), highlightthickness=1,
                            highlightbackground=BORDER, highlightcolor=ACCENT)

        def label(text, fg=MUTED, size=9, **kw):
            return tk.Label(f, text=text, bg=BG, fg=fg, font=(FONT, size), **kw)

        try:
            self._big = tk.PhotoImage(file=os.path.join(ASSETS, "moxy_256.png")).subsample(2, 2)
            tk.Label(f, image=self._big, bg=BG).pack(pady=(40, 4))
        except tk.TclError:
            pass
        tk.Label(f, text="MoxyVPN", bg=BG, fg=TEXT, font=(FONT, 22, "bold")).pack()
        label("Sign in with your Firefox / Mozilla VPN account", size=10).pack(pady=(2, 22))
        label("Email", anchor="w").pack(fill="x", padx=40)
        self.l_email = entry()
        self.l_email.pack(fill="x", padx=40, ipady=7, pady=(2, 12))
        label("Password", anchor="w").pack(fill="x", padx=40)
        self.l_pass = entry("\u2022")
        self.l_pass.pack(fill="x", padx=40, ipady=7, pady=(2, 12))
        self.l_code_label = label("", fg=ACCENT2, anchor="w", justify="left", wraplength=320)
        self.l_code = entry()
        self.l_btn = tk.Button(f, text="Sign in", command=self.do_login, bg=ACCENT, fg="#1B0F05",
                               activebackground=ACCENT2, activeforeground="#1B0F05", relief="flat",
                               bd=0, font=(FONT, 11, "bold"), cursor="hand2")
        self.l_btn.pack(fill="x", padx=40, ipady=8, pady=(6, 8))
        self.l_msg = label("", wraplength=320, justify="center")
        self.l_msg.pack(padx=40)
        self.l_adv = label("Can't connect? Set a sign-in proxy", fg=DIM)
        self.l_adv.config(font=(FONT, 9, "underline"), cursor="hand2")
        self.l_adv.pack(pady=(14, 0))
        self.l_adv.bind("<Button-1>", lambda e: self._show_proxy_field())
        self.l_proxy = entry(var=self.api_proxy_var)
        if self.api_proxy_var.get():
            self._show_proxy_field()
        label("Your password goes only to Firefox Accounts and is never saved. "
              "Only a sign-in token is kept on this PC.", fg=DIM, justify="center",
              wraplength=320).pack(side="bottom", pady=22)
        self.bind("<Return>", self._enter_key)

    def _show_proxy_field(self):
        self.l_adv.config(text="Sign-in proxy (e.g. socks5://127.0.0.1:10808)")
        self.l_proxy.pack(fill="x", padx=40, ipady=5, pady=(4, 0), after=self.l_adv)

    def _enter_key(self, _e=None):
        if self.login_frame.winfo_ismapped():
            self.do_verify() if self.login_ctx else self.do_login()

    def show_login(self, msg=""):
        self.show()
        self.login_ctx = None
        self.l_code_label.pack_forget()
        self.l_code.pack_forget()
        self.l_btn.config(text="Sign in", command=self.do_login)
        self._login_msg(msg, MUTED)
        self.login_frame.place(x=0, y=0, width=W, relheight=1)
        self.login_frame.lift()
        (self.l_pass if self.l_email.get() else self.l_email).focus_set()

    def hide_login(self):
        self.login_frame.place_forget()
        self.l_pass.delete(0, "end")
        self.l_code.delete(0, "end")
        self.login_ctx = None

    def _login_msg(self, text, color=MUTED):
        self.l_msg.config(text=text, fg=color)

    def _login_busy(self, busy, text=None):
        self.login_busy = busy
        if busy:
            self.l_btn.config(state="disabled", text=text or "Please wait...")
        else:
            label = "Sign in" if not self.login_ctx else (
                "Continue" if self.login_ctx["method"] == "email" else "Verify")
            self.l_btn.config(state="normal", text=label)

    def _explain(self, exc):
        try:
            from foxyvpn.exceptions import FxaApiError
        except Exception:
            FxaApiError = ()
        if FxaApiError and isinstance(exc, FxaApiError):
            nice = {102: "No Firefox account exists for this email.",
                    103: "Incorrect password.",
                    114: "Too many attempts. Wait a few minutes and try again.",
                    201: "Firefox Accounts is busy. Try again in a minute."}
            return nice.get(getattr(exc, "errno", None), str(exc))
        name = type(exc).__name__
        if isinstance(exc, OSError) or any(k in name for k in ("Connect", "Timeout", "Proxy", "Network")):
            return ("Can't reach Firefox Accounts. Check your internet connection, "
                    "or set a sign-in proxy below.")
        return f"{name}: {exc}"

    def do_login(self):
        if self.login_busy:
            return
        email, pw = self.l_email.get().strip(), self.l_pass.get()
        if "@" not in email or not pw:
            self._login_msg("Enter your email and password.", RED)
            return
        proxy = self.api_proxy_var.get().strip()
        self.state_data["api_proxy"] = proxy
        self.settings["api_proxy"] = proxy
        self._save_settings()
        self._pending_email = email
        self._login_msg("", MUTED)
        self._login_busy(True, "Signing in...")

        def work():
            try:
                from foxyvpn import fxa, http_client
                http_client.set_control_plane_proxy(proxy or None)
                resp = fxa.login(email, pw)
                if resp.verified:
                    self._finish_login(resp.session_token)
                else:
                    self.q.put(("login_code", {"session": resp.session_token, "email": email,
                                               "method": resp.verification_method or "email-2fa"}))
            except Exception as exc:  # noqa: BLE001
                self.q.put(("login_err", self._explain(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _finish_login(self, session_token):
        from foxyvpn import fxa, tokens
        tokens.save_tokens(fxa.oauth_token(session_token))
        self.q.put(("login_ok", None))

    def _login_need_code(self, ctx):
        self.login_ctx = ctx
        method = ctx["method"]
        if method == "email":
            text = "Open the confirmation link we emailed you, then press Continue."
        elif method == "totp-2fa":
            text = "Enter the 6-digit code from your authenticator app."
        else:
            text = f"Enter the confirmation code we emailed to {ctx['email']}."
        self.l_code_label.config(text=text)
        self.l_code_label.pack(fill="x", padx=40, before=self.l_btn)
        if method != "email":
            self.l_code.pack(fill="x", padx=40, ipady=7, pady=(2, 8), before=self.l_btn)
            self.l_code.focus_set()
        self.l_btn.config(command=self.do_verify)
        self._login_busy(False)
        self._login_msg("", MUTED)

    def do_verify(self):
        ctx = self.login_ctx
        if self.login_busy or not ctx:
            return
        code = self.l_code.get().strip()
        if ctx["method"] != "email" and not code:
            self._login_msg("Enter the code first.", RED)
            return
        self._login_busy(True, "Verifying...")

        def work():
            try:
                from foxyvpn import fxa
                if ctx["method"] == "totp-2fa":
                    fxa._fxa_do("POST", "/session/verify/totp", session_token=ctx["session"],
                                json_body={"code": code})
                elif ctx["method"] != "email":
                    fxa.verify_session(ctx["session"], code)
                self._finish_login(ctx["session"])
            except Exception as exc:  # noqa: BLE001
                self.q.put(("login_err", self._explain(exc)))
        threading.Thread(target=work, daemon=True).start()

    def sign_out(self):
        if not messagebox.askyesno(APP_NAME, "Sign out of this account on this PC?"):
            return
        self.stop()
        try:
            from foxyvpn import tokens
            tokens.delete_tokens()
        except Exception:
            pass
        self.state_data.pop("quota", None)
        self.state_data.pop("history", None)
        self.state_data.pop("email", None)
        self.close_settings(False)
        self.update_header()
        usage.save_state(self.state_data)
        self.render_usage()
        self.l_email.delete(0, "end")
        self.show_login()

    # ------------------------------------------------------------- settings
    def _save_settings(self):
        self.state_data["settings"] = self.settings
        usage.save_state(self.state_data)

    def listen_host(self):
        return self.settings["listen"] or HOST

    def listen_display(self):
        return "127.0.0.1" if self.listen_host() in ("0.0.0.0", "::") else self.listen_host()

    def engine_needed(self):
        return bool(self.use_tun.get() or self.settings["http_on"])

    def set_setting(self, key, value, kind="none"):
        self.settings[key] = value
        self._save_settings()
        if key == "listen":
            self.c.itemconfig(self.addr_item, text=self.listen_host() + " :")
        if key == "api_proxy":
            self.api_proxy_var.set(value)
        self.apply_changes(kind)

    def apply_changes(self, kind):
        if not self.proc:
            return
        if kind == "engine":
            self.stop_tun()
            if self.engine_needed():
                self.start_tun()
            self._log("[settings] applied")
        elif kind == "core":
            self._log("[settings] reconnecting to apply changes")
            self.stop()
            self.after(800, self.start)

    def set_port(self, value):
        self.port_var.set(str(value))
        self.api_port_cache = int(value)
        self.state_data["port"] = str(value)
        self._save_settings()
        self.apply_changes("core")

    def set_proxy_only(self, on):
        self.use_tun.set(not on)
        self.state_data["tun"] = self.use_tun.get()
        self.draw_toggle()
        self._save_settings()
        self.apply_changes("core")

    # ----------------------------------------------------------------- theme
    def toggle_theme(self):
        cur = theme.resolve(self.settings["theme"])
        self.apply_theme("light" if cur == "dark" else "dark")

    def set_theme_pref(self, name):
        self.apply_theme(name)

    def apply_theme(self, pref=None):
        if pref:
            self.settings["theme"] = pref
            self._save_settings()
        apply_palette(self.settings["theme"])
        login_visible = self.login_frame.winfo_ismapped()
        reopen = self.settings_open
        self.settings_page, self.settings_open = None, False
        for w in list(self.winfo_children()):
            w.destroy()
        self.configure(bg=BG)
        self._build()
        self.fx.rebind(self.c)
        self._build_login()
        self.log.config(state="normal")
        self.log.insert("end", "\n".join(self.log_lines) + ("\n" if self.log_lines else ""))
        self.log.see("end")
        self.log.config(state="disabled")
        if self.log_visible:
            self.log_frame.pack(side="right", fill="y")
            self.c.itemconfig(self.logt, text="Hide log  \u25c2")
        self.set_state(self.vstate)
        self.render_usage()
        self.update_split_chip()
        if login_visible:
            self.show_login()
        if reopen:
            self.open_settings(animate=False)

    # ------------------------------------------------------ settings drawer
    def open_settings(self, animate=True):
        if self.settings_open:
            return
        self.settings_open = True
        page = self.settings_page = settings_ui.SettingsPage(self)
        w = W
        if not animate:
            page.place(x=0, y=0, width=w, relheight=1)
            page.lift()
            return
        steps = 9

        def step(i=0):
            if self.settings_page is not page:
                return
            t = (i + 1) / steps
            page.place(x=int(w * (1 - (1 - (1 - t) ** 3))), y=0, width=w, relheight=1)
            page.lift()
            if i + 1 < steps:
                self.after(14, lambda: step(i + 1))
        step()

    def close_settings(self, animate=True):
        page = self.settings_page
        if not page:
            return
        self.settings_page, self.settings_open = None, False
        if not animate:
            page.destroy()
            return
        w = W
        steps = 7

        def step(i=0):
            t = (i + 1) / steps
            try:
                page.place(x=int(w * t ** 2), y=0, width=w, relheight=1)
            except tk.TclError:
                return
            if i + 1 < steps:
                self.after(14, lambda: step(i + 1))
            else:
                page.destroy()
        step()

    def show_log(self):
        if not self.log_visible:
            self.toggle_log()

    def _email_text(self):
        e = self.state_data.get("email")
        if not e:
            return "Firefox VPN client"
        return e if len(e) <= 30 else e[:27] + "\u2026"

    def update_header(self):
        self.c.itemconfig(self.hdr_sub, text=self._email_text())

    # ------------------------------------------------------- split tunneling
    def split_summary(self):
        n = len(self.split["apps"])
        return {"off": "Off", "exclude": f"Bypass {n} app{'s' if n != 1 else ''}",
                "include": f"Only {n} app{'s' if n != 1 else ''}"}[self.split["mode"]] + "  \u203a"

    def update_split_chip(self):
        self.c.itemconfig(self.split_txt, text=self.split_summary())

    def open_split(self):
        SplitDialog(self)

    def set_split(self, mode, apps):
        self.split = {"mode": mode, "apps": apps}
        self.state_data["split"] = self.split
        usage.save_state(self.state_data)
        self.update_split_chip()
        if self.tun:                       # apply right away
            self.stop_tun()
            self.start_tun()
            self._log("[split] rules updated")

    # ------------------------------------------------------------ extension API
    def _start_api(self):
        try:
            _ApiHandler.app = self
            self.api = http.server.ThreadingHTTPServer(("127.0.0.1", API_PORT), _ApiHandler)
            threading.Thread(target=self.api.serve_forever, daemon=True).start()
        except OSError as exc:
            self.api = None
            self._log(f"[api] browser-extension API unavailable: {exc}")

    def api_status(self):
        q = self.state_data.get("quota") or {}
        return {
            "app": APP_NAME, "api": 1, "state": self.vstate, "port": self.api_port_cache,
            "country": self.country_code, "tun": bool(self.tun),
            "signed_in": os.path.exists(TOKENS),
            "usage": {k: q.get(k) for k in ("used", "limit", "left", "reset", "fetched_at")},
        }

    # ---------------------------------------------------------------- events
    def _reader(self, kind, proc):
        for line in proc.stdout:
            self.q.put((kind, proc, line.rstrip()))
        self.q.put((kind, proc, None))

    def _tick(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "ui":
                    item[1]()
                elif kind == "log":
                    self._log(item[1])
                elif kind == "login_code":
                    self._login_need_code(item[1])
                elif kind == "login_err":
                    self._login_busy(False)
                    self._login_msg(item[1], RED)
                elif kind == "login_ok":
                    self._login_busy(False)
                    self.hide_login()
                    if self._pending_email:
                        self.state_data["email"] = self._pending_email
                        usage.save_state(self.state_data)
                        self.update_header()
                    self.refresh_usage()
                    self.start()
                elif kind == "usage":
                    self.fetching = False
                    self.last_fetch = time.time()
                    usage.remember(self.state_data, item[1])
                    self.render_usage()
                elif kind == "usage_err":
                    self.fetching = False
                    self.last_fetch = time.time()
                    self._log("[usage] could not refresh: " + item[1])
                    self.render_usage()
                elif kind == "proxy":
                    _, proc, line = item
                    if proc is not self.proc:
                        continue
                    if line is None:
                        self.stop()
                        if self.need_login:
                            self.show_login("Your session expired - please sign in again.")
                        continue
                    self._log(line)
                    if "Firefox Accounts email" in line:
                        self.need_login = True
                    if "SOCKS5 proxy listening" in line:
                        if self.engine_needed():
                            self.start_tun()
                        self.set_state("on")
                        self.refresh_usage()
                elif kind == "tun":
                    _, proc, line = item
                    if proc is not self.tun:
                        continue
                    if line is None:
                        self.tun = None
                        self._log("[tun] stopped")
                        self._refresh_sub()
                        continue
                    self._log("[tun] " + line)
        except queue.Empty:
            pass
        if time.time() - self.last_fetch > USAGE_REFRESH_SECONDS and self.proc and self.vstate == "on":
            self.refresh_usage()
        if int(time.time()) % 30 == 0:
            self.render_usage()
        self.after(250, self._tick)


def single_instance():
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", 47831))
        s.listen(1)
        return s
    except OSError:
        return None


if __name__ == "__main__":
    lock = single_instance()
    if lock is None:
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo(APP_NAME, "MoxyVPN is already running - look for the fox in the system tray.")
        sys.exit(0)
    App().mainloop()
