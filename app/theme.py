"""Color palettes (dark / light) shared by every window."""
import sys

DARK = dict(BG="#0D1017", CARD="#161A24", FIELD="#0D1017", BORDER="#262C3C",
            TEXT="#EEF0F8", MUTED="#8991AB", DIM="#5B6280",
            ACCENT="#FF7A1A", ACCENT2="#FFB347", GREEN="#35D69A", RED="#FF5C6C")
LIGHT = dict(BG="#F3F4F9", CARD="#FFFFFF", FIELD="#F3F4F9", BORDER="#DCE0EC",
             TEXT="#161A26", MUTED="#5C6482", DIM="#98A0B9",
             ACCENT="#FF7A1A", ACCENT2="#E0620A", GREEN="#13A06E", RED="#E0364B")


class _Colors:
    pass


C = _Colors()          # live palette: C.BG, C.CARD ... (updated by set_theme)


def system_theme():
    """'dark' or 'light' according to the Windows app-mode setting."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return "light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "dark"
    except Exception:
        return "dark"


def resolve(name):
    return system_theme() if name == "system" else ("light" if name == "light" else "dark")


def set_theme(name):
    """Activate a palette and return it as a dict."""
    pal = LIGHT if resolve(name) == "light" else DARK
    for k, v in pal.items():
        setattr(C, k, v)
    return pal


def mix(a, b, t):
    a = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


set_theme("dark")
