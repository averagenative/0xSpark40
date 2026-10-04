"""Visual themes: Spark finishes, other tolex colors, and a few unrelated looks.

A finish theme dresses each panel in tolex (a color with a leather grain), runs piping around
its edge, and puts grille cloth behind the panels. It also overrides libadwaita's color
variables and picks a knob style.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402

TEXTURES = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "spark40" / "themes"
GROUPS = {"spark": "Spark finishes", "tolex": "Tolex colors", "other": "Other looks"}


@dataclass(frozen=True)
class KnobStyle:
    kind: str = "arc"
    track: tuple | None = None
    arc: tuple | None = None
    cap_hi: tuple = (0.2, 0.2, 0.2)
    cap_lo: tuple = (0.05, 0.05, 0.05)
    rim: tuple = (0, 0, 0)
    pointer: tuple = (1, 1, 1)
    text: tuple | None = None
    glow: bool = False


@dataclass(frozen=True)
class Grille:
    """Grille cloth. ``checker``: squares of fg on bg; ``basket``: woven thread pairs; ``mesh``: fine crosshatch."""
    kind: str
    fg: str
    bg: str
    square: float = 0.42
    size: int = 7


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    scheme: Adw.ColorScheme
    group: str = "other"
    knob: KnobStyle = field(default_factory=KnobStyle)
    variables: dict = field(default_factory=dict)
    extra_css: str = ""
    grille: Grille | None = None
    tolex: str | None = None
    piping: str | None = None
    grain: float = 0.12


def rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))


def grille_svg(g: Grille) -> str:
    if g.kind == "checker":
        side = 6 * g.square
        off = (3 - side) / 2
        shapes = (f'<rect width="6" height="6" fill="{g.bg}"/>'
                  f'<g fill="{g.fg}"><rect x="{off:.2f}" y="{off:.2f}" width="{side:.2f}" height="{side:.2f}" rx="0.35"/>'
                  f'<rect x="{3 + off:.2f}" y="{3 + off:.2f}" width="{side:.2f}" height="{side:.2f}" rx="0.35"/></g>')
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="6" height="6" viewBox="0 0 6 6">{shapes}</svg>'
    if g.kind == "mesh":
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4" viewBox="0 0 4 4">'
                f'<rect width="4" height="4" fill="{g.bg}"/>'
                f'<g stroke="{g.fg}" stroke-width="0.55" stroke-linecap="square">'
                '<line x1="0" y1="0" x2="4" y2="4"/><line x1="4" y1="0" x2="0" y2="4"/></g></svg>')
    threads = [
        (0.6, 0.9, 3.0, 1.1), (0.6, 2.5, 3.0, 1.1),      # across, top left
        (4.9, 0.6, 1.1, 3.0), (6.5, 0.6, 1.1, 3.0),      # down, top right
        (0.9, 4.6, 1.1, 3.0), (2.5, 4.6, 1.1, 3.0),      # down, bottom left
        (4.6, 4.9, 3.0, 1.1), (4.6, 6.5, 3.0, 1.1),      # across, bottom right
    ]
    rects = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="0.5"/>' for x, y, w, h in threads)
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8" viewBox="0 0 8 8">'
            f'<rect width="8" height="8" fill="{g.bg}"/><g fill="{g.fg}">{rects}</g></svg>')


def grain_svg(strength: float, seed: int = 7) -> str:
    """Leather grain: a tile of faint light and dark flecks, transparent elsewhere."""
    rnd = random.Random(seed)
    flecks = []
    for _ in range(700):
        x, y = rnd.uniform(0, 64), rnd.uniform(0, 64)
        r = rnd.uniform(0.35, 1.1)
        light = rnd.random() < 0.5
        alpha = strength * rnd.uniform(0.3, 1.0)
        color = "#ffffff" if light else "#000000"
        flecks.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="{color}" fill-opacity="{alpha:.3f}"/>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
            + "".join(flecks) + "</svg>")


GOLD = KnobStyle(kind="cap", track=rgb("#e2bd6b") + (0.18,), arc=rgb("#e2bd6b") + (1.0,),
                 cap_hi=rgb("#f6e2a6"), cap_lo=rgb("#94702e"), rim=rgb("#3e2f12"), pointer=rgb("#1d1609"))
GOLD_ON_LIGHT = KnobStyle(kind="cap", track=rgb("#6b5530") + (0.18,), arc=rgb("#a07a35") + (1.0,),
                          cap_hi=rgb("#f6e2a6"), cap_lo=rgb("#94702e"), rim=rgb("#5a4520"), pointer=rgb("#1d1609"))
BLACK_GOLD = KnobStyle(kind="cap", track=rgb("#e0bf75") + (0.16,), arc=rgb("#e0bf75") + (1.0,),
                       cap_hi=rgb("#454443"), cap_lo=rgb("#0a0a0a"), rim=rgb("#000000"), pointer=rgb("#e8c77d"))
CREAM = KnobStyle(kind="cap", track=rgb("#efe6c8") + (0.18,), arc=rgb("#efe6c8") + (1.0,),
                  cap_hi=rgb("#fffbf0"), cap_lo=rgb("#cfc4a2"), rim=rgb("#7f775f"), pointer=rgb("#2a2620"))
CHROME = KnobStyle(kind="cap", track=rgb("#e8dcc0") + (0.18,), arc=rgb("#e8dcc0") + (1.0,),
                   cap_hi=rgb("#ffffff"), cap_lo=rgb("#868e96"), rim=rgb("#474d53"), pointer=rgb("#14171a"))


def dark_vars(tolex: str, fg: str, accent: str, accent_fg: str = "#141210") -> dict:
    return {
        "window-bg-color": tolex, "window-fg-color": fg,
        "view-bg-color": tolex, "view-fg-color": fg,
        "card-bg-color": tolex, "card-fg-color": fg, "card-shade-color": "rgba(0,0,0,0.5)",
        "headerbar-bg-color": tolex, "headerbar-fg-color": fg,
        "headerbar-backdrop-color": tolex, "headerbar-shade-color": "rgba(0,0,0,0.6)",
        "popover-bg-color": tolex, "popover-fg-color": fg,
        "dialog-bg-color": tolex, "dialog-fg-color": fg,
        "accent-bg-color": accent, "accent-fg-color": accent_fg, "accent-color": accent,
    }


THEMES = [
    Theme(
        id="black", name="Spark 40 Black", group="spark", scheme=Adw.ColorScheme.FORCE_DARK, knob=GOLD,
        tolex="#1d1c1b", piping="#c9a455", grain=0.10,
        grille=Grille("checker", fg="#1b1610", bg="#a9874a", square=0.36),
        variables=dark_vars("#1d1c1b", "#efe6d2", "#c9a455"),
    ),
    Theme(
        id="pearl", name="Spark 40 Pearl", group="spark", scheme=Adw.ColorScheme.FORCE_LIGHT, knob=GOLD_ON_LIGHT,
        tolex="#f3f0ea", piping="#b8954f", grain=0.07,
        grille=Grille("checker", fg="#5b4628", bg="#957a4e", square=0.40),
        variables={
            **dark_vars("#f3f0ea", "#2a2620", "#8a6a32", "#ffffff"),
            "card-shade-color": "rgba(60,45,20,0.25)", "headerbar-shade-color": "rgba(60,45,20,0.2)",
        },
    ),
    Theme(
        id="spark2", name="Spark 2", group="spark", scheme=Adw.ColorScheme.FORCE_DARK, knob=GOLD,
        tolex="#171615", piping="#d6aa4f", grain=0.10,
        grille=Grille("checker", fg="#7d6230", bg="#12110f", square=0.30, size=5),
        variables=dark_vars("#171615", "#efe6d2", "#d6aa4f"),
    ),
    Theme(
        id="vai", name="Spark MINI Vai Red", group="spark", scheme=Adw.ColorScheme.FORCE_DARK, knob=GOLD,
        tolex="#6a1a24", piping="#c9a455", grain=0.14,
        grille=Grille("checker", fg="#a8843f", bg="#0e0d0b", square=0.24, size=6),
        variables=dark_vars("#6a1a24", "#f6e9e0", "#d4b062"),
    ),
    Theme(
        id="live", name="Spark LIVE", group="spark", scheme=Adw.ColorScheme.FORCE_DARK, knob=BLACK_GOLD,
        tolex="#191919", piping="#b8934f", grain=0.10,
        grille=Grille("checker", fg="#c4c3bd", bg="#2b2b2a", square=0.44, size=6),
        variables=dark_vars("#191919", "#ecebe6", "#c9a455"),
    ),
    Theme(
        id="emerald", name="Emerald", group="tolex", scheme=Adw.ColorScheme.FORCE_DARK, knob=CREAM,
        tolex="#0f4a3d", piping="#0a3329", grain=0.14,
        grille=Grille("mesh", fg="#9aa4a7", bg="#0b0e0f", size=5),
        variables=dark_vars("#0f4a3d", "#eef4ee", "#e8dfc0"),
    ),
    Theme(
        id="purple", name="Purple", group="tolex", scheme=Adw.ColorScheme.FORCE_DARK, knob=GOLD,
        tolex="#3b2c82", piping="#d4b25e", grain=0.14,
        grille=Grille("basket", fg="#ebe5d6", bg="#a49d8e", size=9),
        variables=dark_vars("#3b2c82", "#f3f0ff", "#d4b25e"),
    ),
    Theme(
        id="blue", name="Blue", group="tolex", scheme=Adw.ColorScheme.FORCE_DARK, knob=CHROME,
        tolex="#1e2c52", piping="#e6dcc2", grain=0.14,
        grille=Grille("basket", fg="#f1e4bf", bg="#b39d6c", size=9),
        variables=dark_vars("#1e2c52", "#eef1fa", "#e6dcc2"),
    ),
    Theme(
        id="adwaita",
        name="Adwaita",
        scheme=Adw.ColorScheme.DEFAULT,
    ),
    Theme(
        id="neon",
        name="Neon",
        scheme=Adw.ColorScheme.FORCE_DARK,
        knob=KnobStyle(kind="arc", track=rgb("#ff2bd6") + (0.22,), arc=rgb("#00f0ff") + (1.0,),
                       text=rgb("#9ff8ff"), glow=True),
        variables={
            "window-bg-color": "#07070f", "window-fg-color": "#d9f6ff",
            "view-bg-color": "#0b0b18", "view-fg-color": "#d9f6ff",
            "card-bg-color": "#0e0e1f", "card-fg-color": "#d9f6ff", "card-shade-color": "rgba(0,240,255,0.25)",
            "headerbar-bg-color": "#05050b", "headerbar-fg-color": "#ff5be0",
            "popover-bg-color": "#11112a", "popover-fg-color": "#d9f6ff",
            "dialog-bg-color": "#0e0e1f", "dialog-fg-color": "#d9f6ff",
            "accent-bg-color": "#ff2bd6", "accent-fg-color": "#0a0a14", "accent-color": "#ff5be0",
        },
        extra_css="""
.spark-window scrolledwindow.spark-scroller {
  background-color: #07070f;
  background-image: repeating-linear-gradient(0deg, rgba(255,43,214,0.07) 0px, rgba(255,43,214,0.07) 1px, transparent 1px, transparent 32px),
                    repeating-linear-gradient(90deg, rgba(0,240,255,0.06) 0px, rgba(0,240,255,0.06) 1px, transparent 1px, transparent 32px);
}
.spark-window .card {
  border: 1px solid rgba(0,240,255,0.45);
  box-shadow: 0 0 14px rgba(0,240,255,0.18), inset 0 0 18px rgba(255,43,214,0.06);
}
.spark-window .heading { color: #ff5be0; text-shadow: 0 0 8px rgba(255,43,214,0.8); letter-spacing: 0.12em; }
.spark-window .caption { color: #9ff8ff; letter-spacing: 0.02em; }
.spark-window headerbar { box-shadow: inset 0 -1px rgba(255,43,214,0.6); }
""",
    ),
    Theme(
        id="metal",
        name="Bare Metal",
        scheme=Adw.ColorScheme.FORCE_LIGHT,
        knob=KnobStyle(kind="cap", track=rgb("#2c3034") + (0.18,), arc=rgb("#2f3438") + (1.0,),
                       cap_hi=rgb("#f6f7f8"), cap_lo=rgb("#8e959c"), rim=rgb("#5e656c"),
                       pointer=rgb("#1b1e21"), text=rgb("#1b1e21")),
        variables={
            "window-bg-color": "#c3c7cb", "window-fg-color": "#1b1e21",
            "view-bg-color": "#dde0e3", "view-fg-color": "#1b1e21",
            "card-bg-color": "#d3d6d9", "card-fg-color": "#1b1e21", "card-shade-color": "rgba(0,0,0,0.28)",
            "headerbar-bg-color": "#30353a", "headerbar-fg-color": "#e7eaed",
            "popover-bg-color": "#dde0e3", "popover-fg-color": "#1b1e21",
            "dialog-bg-color": "#d3d6d9", "dialog-fg-color": "#1b1e21",
            "accent-bg-color": "#35546e", "accent-fg-color": "#ffffff", "accent-color": "#2c4a63",
        },
        extra_css="""
.spark-window scrolledwindow.spark-scroller {
  background-color: #c3c7cb;
  background-image: repeating-linear-gradient(90deg, rgba(255,255,255,0.18) 0px, rgba(255,255,255,0.18) 1px,
                    rgba(0,0,0,0.04) 1px, rgba(0,0,0,0.04) 2px, transparent 2px, transparent 3px),
                    linear-gradient(170deg, rgba(255,255,255,0.35), rgba(0,0,0,0.12));
}
.spark-window .card {
  border: 1px solid #7b828a;
  background-image: repeating-linear-gradient(90deg, rgba(255,255,255,0.22) 0px, rgba(255,255,255,0.22) 1px,
                    rgba(0,0,0,0.035) 1px, rgba(0,0,0,0.035) 3px);
  box-shadow: inset 0 1px rgba(255,255,255,0.75), inset 0 -1px rgba(0,0,0,0.18), 0 2px 4px rgba(0,0,0,0.3);
}
.spark-window .heading { letter-spacing: 0.08em; color: #2b3035; text-shadow: 0 1px rgba(255,255,255,0.7); }
.spark-window .caption { letter-spacing: 0.02em; font-weight: 700; color: #3a4046; text-shadow: 0 1px rgba(255,255,255,0.6); }
""",
    ),
]

BY_ID = {t.id: t for t in THEMES}
DEFAULT = "black"
_current = BY_ID[DEFAULT]
_listeners: list = []


def current() -> Theme:
    return _current


def on_change(callback) -> None:
    _listeners.append(callback)


def _write(name: str, svg: str) -> Path:
    TEXTURES.mkdir(parents=True, exist_ok=True)
    path = TEXTURES / name
    if not path.exists() or path.read_text() != svg:
        path.write_text(svg)
    return path


HEADER_CSS = """
.spark-window headerbar {
  background-color: var(--headerbar-bg-color);
  color: var(--headerbar-fg-color);
}
"""

FINISH_CSS = """
.spark-window .card {{
  background-color: {tolex};
  background-image: url('{grain}');
  border: 2px solid {piping};
  border-radius: 12px;
  box-shadow: 0 0 0 1px rgba(0,0,0,0.55), 0 3px 10px rgba(0,0,0,0.45);
}}
.spark-window headerbar {{
  background-image: url('{grain}');
  box-shadow: inset 0 -2px {piping}, 0 1px 3px rgba(0,0,0,0.5);
}}
.spark-window .heading {{ letter-spacing: 0.08em; }}
.spark-window .caption {{ letter-spacing: 0.02em; font-weight: 600; }}
.spark-window scrolledwindow.spark-scroller {{
  background-color: shade({tolex}, {shade});
  background-image: url('{grain}');
}}
"""

GRILLE_CSS = """
.spark-window .spark-grille {{
  background-color: {bg};
  background-image: url('{texture}');
  background-size: {size}px {size}px;
  border: 2px solid {piping};
  border-radius: 10px;
  box-shadow: inset 0 0 0 3px rgba(0,0,0,0.85), inset 0 0 18px rgba(0,0,0,0.55), 0 3px 10px rgba(0,0,0,0.45);
}}
.spark-window .spark-badge {{
  background-color: #d3262c;
  background-image: linear-gradient(180deg, rgba(255,255,255,0.18), rgba(0,0,0,0.12));
  color: #ffffff;
  border: 1px solid #f08a8d;
  border-radius: 3px;
  padding: 3px 9px;
  font-weight: 600;
  letter-spacing: 0.04em;
  box-shadow: 0 0 0 1px rgba(0,0,0,0.5), 0 2px 4px rgba(0,0,0,0.5);
}}
"""


def css_for(theme: Theme) -> str:
    lines = [":root {"] + [f"  --{k}: {v};" for k, v in theme.variables.items()] + ["}"]
    if "headerbar-bg-color" in theme.variables:
        lines.append(HEADER_CSS)
    if theme.tolex:
        grain = _write(f"grain-{int(theme.grain * 100)}.svg", grain_svg(theme.grain))
        shade = 0.9 if theme.scheme == Adw.ColorScheme.FORCE_LIGHT else 0.72
        lines.append(FINISH_CSS.format(tolex=theme.tolex, piping=theme.piping or "transparent", grain=grain.as_uri(),
                                       shade=shade))
    if theme.grille:
        texture = _write(f"grille-{theme.id}.svg", grille_svg(theme.grille))
        lines.append(GRILLE_CSS.format(bg=theme.grille.bg, texture=texture.as_uri(), size=theme.grille.size,
                                       piping=theme.piping or "rgba(0,0,0,0.6)"))
    return "\n".join(lines) + "\n" + theme.extra_css


class ThemeManager:
    def __init__(self):
        self.provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)

    def apply(self, theme_id: str) -> Theme:
        global _current
        theme = BY_ID.get(theme_id, BY_ID[DEFAULT])
        self.provider.load_from_string(css_for(theme))
        Adw.StyleManager.get_default().set_color_scheme(theme.scheme)
        _current = theme
        for callback in _listeners:
            callback(theme)
        return theme


_manager: ThemeManager | None = None


def manager() -> ThemeManager:
    global _manager
    if _manager is None:
        _manager = ThemeManager()
    return _manager
