"""Draws every image on the site as SVG, so the repo needs no stock photography.

Run ``python tools/generate_art.py`` to regenerate ``anga/static/images``. Each
scene is composed from a few small shape helpers and a seeded random generator,
which keeps the output byte-for-byte reproducible.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "anga" / "static" / "images"

NIGHT = "#0d1b3e"
TWILIGHT = "#27407f"
DUSK = "#5b4b8a"
AMBER = "#ffb347"
CORAL = "#ff6f61"
ACACIA = "#3f8f6b"
SAND = "#f4d9a8"
SEA = "#2a9d9f"
SEA_DEEP = "#1b6f86"
MIST = "#dfe7f5"


def svg(width: int, height: int, body: str, defs: str = "", label: str = "") -> str:
    title = f"<title>{label}</title>" if label else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" preserveAspectRatio="xMidYMid slice">{title}'
        f"<defs>{defs}</defs>{body}</svg>\n"
    )


def gradient(ident: str, stops: list[tuple[int, str]], x2: int = 0, y2: int = 1) -> str:
    parts = "".join(f'<stop offset="{o}%" stop-color="{c}"/>' for o, c in stops)
    return (
        f'<linearGradient id="{ident}" x1="0" y1="0" x2="{x2}" y2="{y2}">{parts}</linearGradient>'
    )


def rect(x: float, y: float, w: float, h: float, fill: str, extra: str = "") -> str:
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" {extra}/>'


def circle(x: float, y: float, r: float, fill: str, extra: str = "") -> str:
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}" {extra}/>'


def path(d: str, fill: str = "none", extra: str = "") -> str:
    return f'<path d="{d}" fill="{fill}" {extra}/>'


def ridge(
    rng: random.Random, width: int, base: float, amplitude: float, steps: int, height: int
) -> str:
    """A closed, gently undulating silhouette, used for hills and dunes."""
    phase = rng.uniform(0, 6)
    points = [
        (i * width / steps, base + math.sin(phase + i * 0.9) * amplitude * rng.uniform(0.5, 1))
        for i in range(steps + 1)
    ]
    joined = " L".join(f"{x:.1f} {y:.1f}" for x, y in points)
    return f"M0 {height} L{joined} L{width} {height}Z"


def waves(y: float, width: int, colour: str, count: int = 3, gap: float = 14) -> str:
    out = []
    for row in range(count):
        d = f"M0 {y + row * gap:.1f}"
        for _ in range(0, width, 60):
            d += " q15 -5 30 0 t30 0"
        out.append(path(d, extra=f'stroke="{colour}" stroke-width="2" opacity="{0.5 - row * 0.1}"'))
    return "".join(out)


def acacia(x: float, y: float, scale: float, colour: str = NIGHT) -> str:
    """The flat-topped acacia is the brand's recurring landscape signature."""
    trunk = (
        f"M{x:.1f} {y:.1f} C{x + 2 * scale:.1f} {y - 18 * scale:.1f} "
        f"{x - 3 * scale:.1f} {y - 26 * scale:.1f} {x - 16 * scale:.1f} {y - 38 * scale:.1f} "
        f"M{x:.1f} {y - 14 * scale:.1f} C{x + 4 * scale:.1f} {y - 26 * scale:.1f} "
        f"{x + 10 * scale:.1f} {y - 30 * scale:.1f} {x + 20 * scale:.1f} {y - 38 * scale:.1f}"
    )
    crown = (
        f'<ellipse cx="{x + 2 * scale:.1f}" cy="{y - 41 * scale:.1f}" rx="{40 * scale:.1f}" '
        f'ry="{7 * scale:.1f}" fill="{colour}"/>'
        f'<ellipse cx="{x - 12 * scale:.1f}" cy="{y - 45 * scale:.1f}" rx="{20 * scale:.1f}" '
        f'ry="{5 * scale:.1f}" fill="{colour}"/>'
        f'<ellipse cx="{x + 16 * scale:.1f}" cy="{y - 45 * scale:.1f}" rx="{18 * scale:.1f}" '
        f'ry="{4.5 * scale:.1f}" fill="{colour}"/>'
    )
    return path(trunk, extra=f'stroke="{colour}" stroke-width="{3 * scale:.1f}"') + crown


def palm(x: float, y: float, scale: float, colour: str = NIGHT) -> str:
    trunk = (
        f"M{x:.1f} {y:.1f} Q{x + 8 * scale:.1f} {y - 40 * scale:.1f} "
        f"{x + 18 * scale:.1f} {y - 78 * scale:.1f}"
    )
    tip_x, tip_y = x + 18 * scale, y - 78 * scale
    fronds = ""
    for dx, dy in ((-34, 4), (-24, -14), (2, -22), (26, -12), (36, 8), (-14, 18), (16, 20)):
        fronds += path(
            f"M{tip_x:.1f} {tip_y:.1f} Q{tip_x + dx * 0.5 * scale:.1f} "
            f"{tip_y + (dy - 14) * scale:.1f} {tip_x + dx * scale:.1f} {tip_y + dy * scale:.1f} "
            f"Q{tip_x + dx * 0.5 * scale:.1f} {tip_y + (dy - 6) * scale:.1f} "
            f"{tip_x:.1f} {tip_y:.1f}Z",
            colour,
        )
    return path(trunk, extra=f'stroke="{colour}" stroke-width="{3.4 * scale:.1f}"') + fronds


def dhow(x: float, y: float, scale: float, sail: str = "#fff6e6", hull: str = NIGHT) -> str:
    hull_shape = (
        f"M{x - 30 * scale:.1f} {y:.1f} Q{x:.1f} {y + 12 * scale:.1f} {x + 34 * scale:.1f} "
        f"{y - 4 * scale:.1f} L{x + 24 * scale:.1f} {y + 10 * scale:.1f} "
        f"L{x - 22 * scale:.1f} {y + 10 * scale:.1f}Z"
    )
    sail_shape = (
        f"M{x - 2 * scale:.1f} {y - 2 * scale:.1f} L{x + 2 * scale:.1f} {y - 58 * scale:.1f} "
        f"Q{x - 30 * scale:.1f} {y - 30 * scale:.1f} {x - 32 * scale:.1f} {y - 6 * scale:.1f}Z"
    )
    return path(hull_shape, hull) + path(sail_shape, sail)


def airliner(x: float, y: float, scale: float, angle: float, colour: str = "#ffffff") -> str:
    """A side-on airliner, drawn nose-right and then rotated into a climb."""
    fuselage = (
        "M-70 0 C-60 -9 -20 -10 30 -10 C52 -10 66 -6 76 0 C66 5 50 8 30 8 "
        "L-48 8 C-58 8 -66 5 -70 0Z"
    )
    tail = "M-68 -2 L-84 -30 L-68 -30 L-44 -9Z"
    wing = "M-14 2 L-44 34 L-28 34 L22 3Z"
    far_wing = "M-8 -7 L-26 -22 L-16 -22 L14 -8Z"
    windows = "".join(
        f'<rect x="{i}" y="-5.5" width="4" height="3" rx="1" fill="{NIGHT}" opacity=".7"/>'
        for i in range(-40, 44, 8)
    )
    return (
        f'<g transform="translate({x} {y}) rotate({angle}) scale({scale})">'
        + path(far_wing, "#c9d4ea")
        + path(tail, CORAL)
        + path(fuselage, colour)
        + path(wing, "#e6ecf7")
        + windows
        + path("M60 -7 C66 -5 71 -3 76 0 L58 -1Z", NIGHT)
        + "</g>"
    )


def stars(rng: random.Random, width: int, height: int, count: int) -> str:
    return "".join(
        circle(
            rng.uniform(0, width),
            rng.uniform(0, height),
            rng.uniform(0.6, 1.8),
            "#fff",
            f'opacity="{rng.uniform(0.3, 0.9):.2f}"',
        )
        for _ in range(count)
    )


def flight_arc(
    x1: float, y1: float, x2: float, y2: float, bend: float, colour: str, width: float = 2
) -> str:
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - bend
    return path(
        f"M{x1} {y1} Q{mx} {my} {x2} {y2}",
        extra=f'stroke="{colour}" stroke-width="{width}" stroke-dasharray="3 9" '
        'stroke-linecap="round"',
    )


# ---------------------------------------------------------------- brand assets


def logo_mark(size: int = 64, ink: str = NIGHT) -> str:
    """An A formed by a flight path climbing over the horizon."""
    defs = gradient("g", [(0, AMBER), (100, CORAL)], x2=1, y2=1)
    body = (
        path(
            "M10 52 L30 12 Q32 8 34 12 L54 52",
            extra=f'stroke="{ink}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"',
        )
        + path(
            "M6 44 Q30 20 60 16", extra='stroke="url(#g)" stroke-width="6" stroke-linecap="round"'
        )
        + circle(60, 16, 4.5, CORAL)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 66 64" width="{size}" '
        f'height="{size}" role="img"><title>Anga Air</title><defs>{defs}</defs>{body}</svg>\n'
    )


def favicon() -> str:
    defs = gradient("g", [(0, AMBER), (100, CORAL)], x2=1, y2=1)
    body = (
        f'<rect width="64" height="64" rx="14" fill="{NIGHT}"/>'
        + path(
            "M14 50 L30 16 Q32 12 34 16 L50 50",
            extra='stroke="#fff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"',
        )
        + path(
            "M10 42 Q30 24 56 18", extra='stroke="url(#g)" stroke-width="5" stroke-linecap="round"'
        )
    )
    opening = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    return f"{opening}<defs>{defs}</defs>{body}</svg>\n"


# ------------------------------------------------------------------- hero scene


def hero() -> str:
    width, height = 1600, 820
    rng = random.Random(7)
    defs = (
        gradient(
            "sky",
            [(0, NIGHT), (34, TWILIGHT), (56, DUSK), (74, CORAL), (90, AMBER), (100, "#ffd98a")],
        )
        + '<radialGradient id="sun" cx="50%" cy="50%" r="50%">'
        '<stop offset="0%" stop-color="#fff3c4"/><stop offset="40%" stop-color="#ffd27a"/>'
        '<stop offset="100%" stop-color="#ffb347" stop-opacity="0"/></radialGradient>'
        + gradient("runway", [(0, "#1a2448"), (100, "#0a1230")])
    )
    body = rect(0, 0, width, height, "url(#sky)")
    body += stars(rng, width, 300, 120)
    body += circle(1120, 590, 300, "url(#sun)")
    body += circle(1120, 590, 62, "#fff0c2", 'opacity=".95"')

    for y, opacity, w in ((430, 0.25, 460), (500, 0.3, 620), (365, 0.16, 320)):
        x = rng.uniform(120, 860)
        body += (
            f'<ellipse cx="{x:.0f}" cy="{y}" rx="{w / 2}" ry="9" fill="#fff" opacity="{opacity}"/>'
        )

    body += path(ridge(rng, width, 640, 26, 18, height), DUSK, 'opacity=".55"')
    body += path(ridge(rng, width, 668, 18, 22, height), "#32295f", 'opacity=".85"')

    # Control tower and terminal on the horizon.
    body += rect(220, 560, 18, 130, "#1b1f49") + rect(200, 540, 58, 24, "#1b1f49")
    body += rect(205, 544, 48, 10, AMBER, 'opacity=".85"')
    body += path("M196 540 L262 540 L250 528 L208 528Z", "#141a3e")
    body += rect(280, 640, 340, 50, "#1b1f49") + path("M280 640 Q450 600 620 640Z", "#232a5c")
    for x in range(296, 606, 26):
        body += rect(x, 654, 14, 16, AMBER, 'opacity=".7"')

    body += path(ridge(rng, width, 700, 10, 26, height), "#141a3e")
    for x, scale in ((90, 1.5), (760, 1.15), (1010, 0.9), (1400, 1.7), (1540, 1.1)):
        body += acacia(x, 712, scale, "#0c1230")

    # Runway receding towards the horizon, with its centre line lights.
    body += path(f"M360 {height} L760 708 L900 708 L1320 {height}Z", "url(#runway)")
    for i in range(9):
        t = i / 9
        y = 714 + (height - 714) * t * t
        half = 2 + 12 * t * t
        body += rect(828 - half / 2, y, half, 6 + 18 * t * t, "#ffe9b5", 'opacity=".85"')

    body += flight_arc(560, 690, 1250, 270, 170, "#ffffff", 2.5)
    body += airliner(1250, 270, 1.65, -20)
    return svg(width, height, body, defs, "An airliner climbs from a savannah runway at sunset")


# ---------------------------------------------------------------- destinations


def _scene(sky_top: str, sky_bottom: str, sun: tuple[float, float, float] | None = None) -> tuple:
    defs = gradient("sky", [(0, sky_top), (100, sky_bottom)])
    body = rect(0, 0, 480, 320, "url(#sky)")
    if sun:
        body += circle(*sun, "#fff1c9", 'opacity=".95"')
        body += circle(sun[0], sun[1], sun[2] * 1.7, "#fff1c9", 'opacity=".2"')
    return defs, body


def dest_nbo() -> tuple:
    rng = random.Random(1)
    defs, body = _scene(TWILIGHT, AMBER, (360, 150, 34))
    body += path(ridge(rng, 480, 230, 8, 8, 320), DUSK)
    x = 70
    for w, h in (
        (34, 80),
        (26, 112),
        (42, 140),
        (30, 96),
        (36, 164),
        (28, 104),
        (40, 124),
        (30, 74),
    ):
        body += rect(x, 240 - h, w, h + 10, NIGHT)
        for wy in range(int(250 - h), 232, 16):
            for wx in range(x + 5, x + w - 6, 9):
                if rng.random() > 0.45:
                    body += rect(wx, wy, 4, 7, AMBER, 'opacity=".85"')
        x += w + 3
    body += path(ridge(rng, 480, 268, 6, 8, 320), "#3a5f4b")
    body += acacia(50, 285, 1.1, NIGHT) + acacia(420, 292, 0.85, NIGHT)
    return defs, body, "Nairobi skyline beside the national park"


def dest_mba() -> tuple:
    defs, body = _scene("#6fc3df", "#fde3b5", (110, 90, 30))
    body += rect(0, 196, 480, 124, SEA) + waves(214, 480, "#fff")
    body += path("M0 272 Q180 240 480 290 L480 320 L0 320Z", SAND)
    body += dhow(320, 200, 1.1)
    # The tusks arch that greets visitors to Mombasa, abstracted.
    body += path(
        "M60 262 Q80 170 140 162", extra='stroke="#fff6e6" stroke-width="10" stroke-linecap="round"'
    )
    body += path(
        "M210 268 Q190 172 134 162",
        extra='stroke="#fff6e6" stroke-width="10" stroke-linecap="round"',
    )
    body += palm(420, 296, 1.1, NIGHT)
    return defs, body, "Mombasa's arching tusks and an Indian Ocean dhow"


def dest_kis() -> tuple:
    defs, body = _scene("#f6a97a", "#ffd9a0", (240, 170, 44))
    body += rect(0, 186, 480, 134, SEA_DEEP)
    body += rect(190, 186, 100, 134, "#ffd9a0", 'opacity=".25"')
    body += waves(210, 480, "#ffe8c7", 4, 20)
    for x, y, s in ((90, 240, 1.0), (360, 262, 1.25)):
        body += path(
            f"M{x - 34 * s} {y} Q{x} {y + 14 * s} {x + 34 * s} {y} "
            f"L{x + 26 * s} {y + 10 * s} L{x - 26 * s} {y + 10 * s}Z",
            NIGHT,
        )
        body += path(f"M{x} {y} L{x} {y - 34 * s}", extra=f'stroke="{NIGHT}" stroke-width="2"')
    return defs, body, "Fishing boats on Lake Victoria at Kisumu"


def dest_edl() -> tuple:
    rng = random.Random(4)
    defs, body = _scene("#8fc7e8", "#e8f3df", (390, 70, 24))
    body += path(ridge(rng, 480, 170, 14, 7, 320), "#7da98f")
    body += path(ridge(rng, 480, 212, 10, 8, 320), "#5e9a72")
    for row in range(5):
        y = 236 + row * 18
        body += path(
            f"M0 {y} Q240 {y - 16} 480 {y}",
            extra=f'stroke="{ACACIA}" stroke-width="9" opacity="{0.9 - row * 0.1}"',
        )
    body += path(ridge(rng, 480, 286, 4, 8, 320), "#c76f49")
    return defs, body, "Tea and wheat fields in the Eldoret highlands"


def dest_myd() -> tuple:
    defs, body = _scene("#7ad0d8", "#fff0cf", (70, 70, 26))
    body += rect(0, 180, 480, 140, SEA) + waves(198, 480, "#fff", 3, 16)
    body += path("M0 262 Q240 218 480 268 L480 320 L0 320Z", SAND)
    # Vasco da Gama pillar on its coral headland.
    body += path("M300 240 Q350 208 420 250 L420 262 L300 262Z", "#b48a63")
    body += path("M352 222 L356 130 L364 130 L368 222Z", "#fff8ea")
    body += rect(350, 122, 20, 9, CORAL)
    body += palm(90, 288, 1.15, NIGHT)
    return defs, body, "Malindi's coral headland and pillar"


def dest_uka() -> tuple:
    defs, body = _scene("#5fc6e0", "#d6f3ee", (400, 70, 26))
    body += rect(0, 154, 480, 166, "#39bfc0")
    body += rect(0, 154, 480, 34, "#1f8aa5")
    body += waves(202, 480, "#fff", 3, 18)
    body += path("M0 250 Q250 208 480 262 L480 320 L0 320Z", "#fbecd0")
    body += palm(46, 306, 1.45, "#22425a") + palm(120, 300, 1.05, "#22425a")
    body += path("M300 288 q40 -30 80 0Z", CORAL) + path(
        "M340 288 L340 310", extra=f'stroke="{NIGHT}" stroke-width="3"'
    )
    return defs, body, "Diani's white sand and turquoise lagoon"


def dest_lau() -> tuple:
    defs, body = _scene("#f7b48a", "#ffe3ba", (120, 120, 30))
    body += rect(0, 196, 480, 124, SEA_DEEP) + waves(214, 480, "#ffe7c6", 4, 16)
    x = 240
    for w, h in ((46, 62), (38, 88), (54, 52), (44, 74)):
        body += rect(x, 200 - h, w, h, "#fff4e0")
        body += rect(x + w / 2 - 6, 200 - 24, 12, 24, "#7a4a2b", 'rx="6"')
        body += rect(x + 6, 200 - h + 10, 9, 13, TWILIGHT, 'rx="4"')
        x += w
    body += dhow(130, 250, 1.35, "#fffaf0")
    return defs, body, "Lamu's Swahili stone town and a dhow"


def dest_znz() -> tuple:
    defs, body = _scene("#2e7fa8", "#ffe1b0", None)
    body += rect(0, 0, 480, 320, "url(#sky)")
    # A carved Zanzibari door framed against the sea.
    body += rect(0, 216, 480, 104, SEA)
    body += waves(236, 480, "#fff", 3, 18)
    body += path("M150 320 L150 120 Q240 30 330 120 L330 320Z", "#6e3f22")
    body += path("M170 320 L170 128 Q240 58 310 128 L310 320Z", "#8b5530")
    body += path("M240 320 L240 86", extra='stroke="#4f2b14" stroke-width="5"')
    for y in range(146, 320, 36):
        for x in (190, 222, 258, 290):
            body += circle(x, y, 5, AMBER)
    return defs, body, "A carved Stone Town door above the sea at Zanzibar"


def dest_dar() -> tuple:
    defs, body = _scene("#ffa16b", "#ffe2a8", (390, 110, 32))
    x = 30
    for w, h in ((28, 54), (38, 82), (24, 120), (40, 74), (32, 100), (26, 60)):
        body += rect(x, 200 - h, w, h, TWILIGHT)
        x += w + 8
    body += rect(0, 198, 480, 122, SEA_DEEP) + waves(218, 480, "#ffe8c7", 4, 18)
    body += rect(330, 186, 90, 14, CORAL) + rect(346, 150, 8, 40, NIGHT)
    body += path("M290 200 L450 200 L430 226 L306 226Z", NIGHT)
    body += dhow(120, 262, 1.1)
    return defs, body, "Dar es Salaam's harbour at golden hour"


def dest_jro() -> tuple:
    rng = random.Random(10)
    defs, body = _scene("#3f6fb5", "#fdd6a0", (92, 72, 22))
    body += path("M20 262 L190 112 Q240 72 290 112 L470 262Z", "#5a5f8c")
    body += path(
        "M190 112 Q240 72 290 112 L320 136 L290 128 L268 148 L240 124 L214 150 L190 132 L160 138Z",
        "#ffffff",
    )
    body += '<ellipse cx="120" cy="166" rx="86" ry="10" fill="#fff" opacity=".65"/>'
    body += '<ellipse cx="380" cy="184" rx="96" ry="11" fill="#fff" opacity=".6"/>'
    body += path(ridge(rng, 480, 262, 6, 8, 320), "#b8894f")
    for x, s in ((70, 1.25), (250, 0.8), (410, 1.5)):
        body += acacia(x, 290, s, NIGHT)
    return defs, body, "Kilimanjaro's snow cap above the acacia plain"


def dest_ebb() -> tuple:
    rng = random.Random(11)
    defs, body = _scene("#7cc9d4", "#e7f6d9", (380, 76, 24))
    body += path(ridge(rng, 480, 170, 12, 7, 320), "#5f9e6e")
    body += rect(0, 192, 480, 128, "#2e8fa3") + waves(212, 480, "#fff", 3, 20)
    # A grey crowned crane, Uganda's national bird.
    body += path("M120 300 L128 244 M142 300 L136 244", extra=f'stroke="{NIGHT}" stroke-width="3"')
    body += path("M104 214 Q130 178 170 218 Q150 254 116 246Z", "#d7dde8")
    body += path(
        "M162 216 Q190 188 192 150",
        extra='stroke="#d7dde8" stroke-width="8" stroke-linecap="round"',
    )
    body += circle(192, 146, 9, NIGHT) + circle(186, 134, 9, AMBER)
    body += path("M198 146 L216 152 L198 152Z", NIGHT)
    return defs, body, "A crowned crane on the shore of Lake Victoria"


def dest_kgl() -> tuple:
    rng = random.Random(12)
    defs, body = _scene("#a5d3ee", "#fbeec9", (108, 80, 26))
    for base, colour in ((158, "#9cc7a4"), (190, "#7fb48a"), (226, "#5f9e6e"), (262, "#468458")):
        body += path(ridge(rng, 480, base, 26, 5, 320), colour)
    for _ in range(22):
        x, y = rng.uniform(40, 440), rng.uniform(196, 262)
        body += rect(x, y, 9, 7, "#fff5e6") + path(
            f"M{x - 2:.1f} {y:.1f} L{x + 4.5:.1f} {y - 5:.1f} L{x + 11:.1f} {y:.1f}Z", CORAL
        )
    return defs, body, "Kigali's thousand green hills"


DESTINATIONS = {
    "nbo": dest_nbo,
    "mba": dest_mba,
    "kis": dest_kis,
    "edl": dest_edl,
    "myd": dest_myd,
    "uka": dest_uka,
    "lau": dest_lau,
    "znz": dest_znz,
    "dar": dest_dar,
    "jro": dest_jro,
    "ebb": dest_ebb,
    "kgl": dest_kgl,
}


# ---------------------------------------------------------------- empty states


def empty_state(kind: str) -> str:
    """Small illustrations built around the flight-path arc motif."""
    defs = gradient("g", [(0, AMBER), (100, CORAL)], x2=1, y2=0)
    body = path(
        "M20 150 Q160 10 300 150",
        extra='stroke="url(#g)" stroke-width="3" stroke-dasharray="4 10" stroke-linecap="round"',
    )
    body += circle(20, 150, 6, CORAL) + circle(300, 150, 6, AMBER)
    if kind == "search":
        body += airliner(160, 66, 0.55, 0, TWILIGHT)
        body += circle(160, 120, 24, "none", f'stroke="{TWILIGHT}" stroke-width="5"')
        body += path(
            "M178 138 L198 158",
            extra=f'stroke="{TWILIGHT}" stroke-width="6" stroke-linecap="round"',
        )
    elif kind == "trips":
        body += airliner(160, 66, 0.55, -8, TWILIGHT)
        body += rect(120, 104, 80, 46, TWILIGHT, 'rx="8" opacity=".9"')
        body += rect(144, 92, 32, 14, "none", f'rx="4" stroke="{TWILIGHT}" stroke-width="4"')
        body += path("M120 124 L200 124", extra='stroke="#fff" stroke-width="3"')
    elif kind == "inbox":
        body += rect(112, 88, 96, 64, TWILIGHT, 'rx="8" opacity=".9"')
        body += path(
            "M114 92 L160 126 L206 92",
            extra='stroke="#fff" stroke-width="4" stroke-linejoin="round"',
        )
    else:
        body += airliner(160, 96, 0.8, -12, TWILIGHT)
    return svg(320, 170, body, defs)


def write(name: str, content: str) -> None:
    (OUTPUT / name).write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    (OUTPUT / "destinations").mkdir(parents=True, exist_ok=True)
    (OUTPUT / "empty").mkdir(parents=True, exist_ok=True)
    write("logo.svg", logo_mark())
    write("logo-light.svg", logo_mark(ink="#ffffff"))
    write("favicon.svg", favicon())
    write("hero.svg", hero())
    for code, scene in DESTINATIONS.items():
        defs, body, label = scene()
        write(f"destinations/{code}.svg", svg(480, 320, body, defs, label))
    for kind in ("search", "trips", "inbox", "flight"):
        write(f"empty/{kind}.svg", empty_state(kind))
    print(f"Wrote artwork to {OUTPUT}")


if __name__ == "__main__":
    main()
