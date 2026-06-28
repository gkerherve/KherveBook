"""SVG drawing examples (Examples menu, "Drawing" category).

A self-contained companion to ``examples.py``: each builder returns a
list of cell dicts — a markdown heading plus one (occasionally two)
``svg`` cell whose source is a complete static SVG 1.1 document. The
drawings are rendered by Qt's ``QSvgRenderer`` (see ``svgcell.py``), so
they use only static SVG primitives — no script, foreignObject, SMIL or
CSS animation. They show off what an SVG cell can hold: labelled
diagrams, icon grids, gradient art, hand-built charts and tiling
patterns, using the KherveBook brand blue ``#3776ab`` and orange
``#e07b39`` where it reads well.

This module defines its own ``_md``/``_svg`` helpers and exports
``SVG_EXAMPLES`` so it can be merged into ``examples.py`` without a
circular import.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

# KherveBook brand palette, reused below.
BLUE = "#3776ab"
ORANGE = "#e07b39"


def _md(t):
    return {"type": "markdown", "source": t}


def _svg(s):
    return {"type": "svg", "source": s}


# -- 1. Labelled scientific diagram: Bohr atom -----------------------------

BOHR_SVG = '''\
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 460 360" width="460" height="360">
  <defs>
    <radialGradient id="bohrBg" cx="50%" cy="42%" r="75%">
      <stop offset="0" stop-color="#10243a"/>
      <stop offset="1" stop-color="#04101d"/>
    </radialGradient>
    <radialGradient id="nucleus" cx="38%" cy="34%" r="70%">
      <stop offset="0" stop-color="#ffd9a8"/>
      <stop offset="0.45" stop-color="#e07b39"/>
      <stop offset="1" stop-color="#9c4a16"/>
    </radialGradient>
  </defs>
  <rect x="0" y="0" width="460" height="360" fill="url(#bohrBg)"/>
  <g fill="none" stroke="#5b8fc0" stroke-width="1.5">
    <ellipse cx="230" cy="170" rx="70"  ry="70"  opacity="0.85"/>
    <ellipse cx="230" cy="170" rx="120" ry="120" opacity="0.6"/>
    <ellipse cx="230" cy="170" rx="170" ry="120" opacity="0.45"
             transform="rotate(35 230 170)"/>
  </g>
  <!-- nucleus -->
  <circle cx="230" cy="170" r="26" fill="url(#nucleus)"/>
  <text x="230" y="176" font-family="sans-serif" font-size="16"
        font-weight="bold" fill="#3a1a06" text-anchor="middle">+</text>
  <!-- electrons on the shells -->
  <g fill="#9fd0ff" stroke="#3776ab" stroke-width="1.5">
    <circle cx="300" cy="170" r="8"/>
    <circle cx="143" cy="252" r="8"/>
    <circle cx="148" cy="105" r="8"/>
    <circle cx="372" cy="116" r="8"/>
  </g>
  <!-- labels -->
  <g font-family="sans-serif" fill="#dce8f5">
    <text x="230" y="330" font-size="20" font-weight="bold"
          text-anchor="middle">Bohr model of the atom</text>
    <text x="306" y="160" font-size="12" fill="#9fd0ff">e&#8315;</text>
    <text x="252" y="172" font-size="12" fill="#ffd9a8">nucleus</text>
  </g>
  <!-- leader line + shell labels -->
  <line x1="300" y1="240" x2="356" y2="282" stroke="#5b8fc0"
        stroke-width="1" stroke-dasharray="3 3"/>
  <text x="360" y="286" font-family="sans-serif" font-size="12"
        fill="#dce8f5">n = 1, 2, 3 shells</text>
</svg>'''


def _bohr_atom():
    return [
        _md("# Bohr Atom\nA labelled scientific diagram drawn entirely "
            "in static SVG — nested orbital shells, a gradient nucleus "
            "and electrons."),
        _svg(BOHR_SVG),
    ]


# -- 2. Icon / logo grid ----------------------------------------------------

ICON_GRID_SVG = '''\
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 480 340" width="480" height="340">
  <rect x="0" y="0" width="480" height="340" rx="16" fill="#f4f7fb"/>
  <text x="240" y="40" font-family="sans-serif" font-size="20"
        font-weight="bold" fill="#2e3440" text-anchor="middle">Flat icon grid</text>
  <!-- row 1 -->
  <g transform="translate(60,90)">
    <circle cx="0" cy="0" r="34" fill="#3776ab"/>
    <!-- home -->
    <path d="M-15 4 L0 -12 L15 4 Z" fill="#fff"/>
    <rect x="-11" y="2" width="22" height="14" fill="#fff"/>
    <rect x="-3" y="6" width="6" height="10" fill="#3776ab"/>
  </g>
  <g transform="translate(180,90)">
    <circle cx="0" cy="0" r="34" fill="#e07b39"/>
    <!-- star -->
    <polygon fill="#fff" points="0,-18 5,-5 19,-5 8,4 12,17 0,9 -12,17 -8,4 -19,-5 -5,-5"/>
  </g>
  <g transform="translate(300,90)">
    <circle cx="0" cy="0" r="34" fill="#50bea0"/>
    <!-- heart -->
    <path d="M0 14 C-18 0 -14 -16 0 -6 C14 -16 18 0 0 14 Z" fill="#fff"/>
  </g>
  <g transform="translate(420,90)">
    <circle cx="0" cy="0" r="34" fill="#9b59b6"/>
    <!-- gear -->
    <g fill="#fff">
      <circle cx="0" cy="0" r="13"/>
      <rect x="-3" y="-20" width="6" height="40"/>
      <rect x="-20" y="-3" width="40" height="6"/>
      <rect x="-3" y="-20" width="6" height="40" transform="rotate(45)"/>
      <rect x="-20" y="-3" width="40" height="6" transform="rotate(45)"/>
    </g>
    <circle cx="0" cy="0" r="6" fill="#9b59b6"/>
  </g>
  <!-- row 2 -->
  <g transform="translate(60,210)">
    <circle cx="0" cy="0" r="34" fill="#e74c3c"/>
    <!-- bell -->
    <path d="M-12 8 C-12 -6 -8 -14 0 -14 C8 -14 12 -6 12 8 Z" fill="#fff"/>
    <rect x="-14" y="8" width="28" height="4" rx="2" fill="#fff"/>
    <circle cx="0" cy="15" r="4" fill="#fff"/>
  </g>
  <g transform="translate(180,210)">
    <circle cx="0" cy="0" r="34" fill="#f1c40f"/>
    <!-- bolt -->
    <polygon fill="#fff" points="4,-18 -10,4 -1,4 -4,18 12,-6 2,-6"/>
  </g>
  <g transform="translate(300,210)">
    <circle cx="0" cy="0" r="34" fill="#1abc9c"/>
    <!-- check -->
    <polyline points="-14,2 -4,12 14,-10" fill="none" stroke="#fff"
              stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
  </g>
  <g transform="translate(420,210)">
    <circle cx="0" cy="0" r="34" fill="#34495e"/>
    <!-- mail -->
    <rect x="-16" y="-11" width="32" height="22" rx="3" fill="#fff"/>
    <polyline points="-16,-9 0,4 16,-9" fill="none" stroke="#34495e"
              stroke-width="3"/>
  </g>
</svg>'''


def _icon_grid():
    return [
        _md("# Icon Grid\nEight flat round icons built from circles, "
            "paths, polygons and `transform` rotations — no font icons, "
            "just SVG shapes."),
        _svg(ICON_GRID_SVG),
    ]


# -- 3. Gradient / abstract art --------------------------------------------

ABSTRACT_SVG = '''\
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 480 320" width="480" height="320">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0"   stop-color="#1b2a4a"/>
      <stop offset="0.55" stop-color="#3776ab"/>
      <stop offset="0.78" stop-color="#e07b39"/>
      <stop offset="1"   stop-color="#ffd9a8"/>
    </linearGradient>
    <radialGradient id="sun" cx="50%" cy="50%" r="50%">
      <stop offset="0"   stop-color="#fff6e0"/>
      <stop offset="0.5" stop-color="#ffd27f"/>
      <stop offset="1"   stop-color="#e07b39" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="sea" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0d3b66"/>
      <stop offset="1" stop-color="#04111f"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="480" height="200" fill="url(#sky)"/>
  <circle cx="240" cy="170" r="120" fill="url(#sun)"/>
  <circle cx="240" cy="148" r="46" fill="#fff1d0"/>
  <rect x="0" y="200" width="480" height="120" fill="url(#sea)"/>
  <!-- rolling hills as translucent layers -->
  <path d="M0 210 Q120 178 240 206 T480 200 V320 H0 Z"
        fill="#3776ab" opacity="0.55"/>
  <path d="M0 232 Q140 204 280 230 T480 224 V320 H0 Z"
        fill="#27506f" opacity="0.7"/>
  <path d="M0 258 Q160 236 320 258 T480 250 V320 H0 Z"
        fill="#16344a"/>
  <!-- sun reflection on the water -->
  <g fill="#ffe0a3" opacity="0.5">
    <rect x="225" y="212" width="30" height="5" rx="2"/>
    <rect x="220" y="226" width="40" height="5" rx="2"/>
    <rect x="214" y="242" width="52" height="5" rx="2"/>
  </g>
</svg>'''


def _abstract():
    return [
        _md("# Gradient Sunset\nLayered linear and radial gradients make "
            "an abstract sunset — soft sky, a glowing sun and "
            "translucent hills."),
        _svg(ABSTRACT_SVG),
    ]


# -- 4. A chart drawn as SVG: bar chart ------------------------------------

def _bar_chart_svg():
    """Build a labelled bar chart by hand (axes, gridlines, value tags)."""
    data = [("Mon", 42), ("Tue", 58), ("Wed", 35),
            ("Thu", 71), ("Fri", 64), ("Sat", 49), ("Sun", 30)]
    w, h = 480, 320
    left, right, top, bottom = 50, 24, 50, 56
    plot_h = h - top - bottom
    plot_w = w - left - right
    vmax = 80
    n = len(data)
    slot = plot_w / n
    bw = slot * 0.6
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {w} {h}" width="{w}" height="{h}">',
        f'  <rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>',
        '  <defs><linearGradient id="barFill" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{ORANGE}"/>'
        f'<stop offset="1" stop-color="{BLUE}"/>'
        '</linearGradient></defs>',
        f'  <text x="{w/2:.0f}" y="30" font-family="sans-serif" '
        'font-size="18" font-weight="bold" fill="#2e3440" '
        'text-anchor="middle">Weekly visitors</text>',
    ]
    # gridlines + y axis labels
    for g in range(0, vmax + 1, 20):
        y = top + plot_h * (1 - g / vmax)
        parts.append(
            f'  <line x1="{left}" y1="{y:.1f}" x2="{w-right}" y2="{y:.1f}" '
            'stroke="#e3e8ef" stroke-width="1"/>')
        parts.append(
            f'  <text x="{left-8}" y="{y+4:.1f}" font-family="sans-serif" '
            'font-size="11" fill="#7a8699" text-anchor="end">'
            f'{g}</text>')
    # axes
    parts.append(
        f'  <line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" '
        'stroke="#2e3440" stroke-width="1.5"/>')
    parts.append(
        f'  <line x1="{left}" y1="{top+plot_h}" x2="{w-right}" '
        f'y2="{top+plot_h}" stroke="#2e3440" stroke-width="1.5"/>')
    # bars + labels
    for i, (label, val) in enumerate(data):
        bh = plot_h * val / vmax
        x = left + slot * i + (slot - bw) / 2
        y = top + plot_h - bh
        parts.append(
            f'  <rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" '
            f'height="{bh:.1f}" rx="3" fill="url(#barFill)"/>')
        parts.append(
            f'  <text x="{x+bw/2:.1f}" y="{y-6:.1f}" '
            'font-family="sans-serif" font-size="11" font-weight="bold" '
            f'fill="#2e3440" text-anchor="middle">{val}</text>')
        parts.append(
            f'  <text x="{x+bw/2:.1f}" y="{top+plot_h+18:.0f}" '
            'font-family="sans-serif" font-size="12" fill="#52606d" '
            f'text-anchor="middle">{label}</text>')
    parts.append('</svg>')
    return "\n".join(parts)


BAR_CHART_SVG = _bar_chart_svg()


def _bar_chart():
    return [
        _md("# SVG Bar Chart\nA bar chart assembled from `<rect>` bars, "
            "`<line>` axes and gridlines, and `<text>` labels — no "
            "plotting library, just SVG."),
        _svg(BAR_CHART_SVG),
    ]


# -- 5. Geometric tiling pattern using <pattern> ---------------------------

TILING_SVG = '''\
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 420 360" width="420" height="360">
  <defs>
    <pattern id="trihex" width="60" height="52" patternUnits="userSpaceOnUse">
      <rect width="60" height="52" fill="#f4f7fb"/>
      <polygon points="30,2 58,18 58,50 30,52 2,50 2,18"
               fill="none" stroke="#3776ab" stroke-width="1.4"/>
      <line x1="30" y1="2"  x2="30" y2="26" stroke="#e07b39" stroke-width="1"/>
      <line x1="58" y1="18" x2="30" y2="26" stroke="#e07b39" stroke-width="1"/>
      <line x1="2"  y1="18" x2="30" y2="26" stroke="#e07b39" stroke-width="1"/>
      <circle cx="30" cy="26" r="3" fill="#e07b39"/>
    </pattern>
    <pattern id="dots" width="26" height="26" patternUnits="userSpaceOnUse">
      <rect width="26" height="26" fill="#ffffff"/>
      <circle cx="6"  cy="6"  r="3" fill="#3776ab"/>
      <circle cx="19" cy="19" r="3" fill="#e07b39"/>
    </pattern>
  </defs>
  <rect x="0" y="0" width="420" height="360" fill="url(#dots)"/>
  <rect x="30" y="30" width="360" height="220" rx="10"
        fill="url(#trihex)" stroke="#2e3440" stroke-width="2"/>
  <text x="210" y="300" font-family="sans-serif" font-size="20"
        font-weight="bold" fill="#2e3440" text-anchor="middle">Tiling with &lt;pattern&gt;</text>
  <text x="210" y="326" font-family="sans-serif" font-size="13"
        fill="#52606d" text-anchor="middle">a repeating tile fills the panel; dots fill the page</text>
</svg>'''


def _tiling():
    return [
        _md("# Tiling Pattern\nTwo `<pattern>` definitions — a hexagon "
            "lattice and a polka-dot fill — repeated across shapes via "
            "`fill=\"url(#id)\"`."),
        _svg(TILING_SVG),
    ]


# -- 6. Annotated figure: a labelled sine wave -----------------------------

def _wave_svg():
    """A sine wave on labelled axes with amplitude/period annotations."""
    import math
    w, h = 500, 300
    cx0, cy0 = 60, h / 2            # axis origin
    plot_w = 400
    amp = 80
    period_px = 200                # one wavelength in pixels
    pts = []
    for i in range(0, plot_w + 1, 4):
        x = cx0 + i
        y = cy0 - amp * math.sin(2 * math.pi * i / period_px)
        pts.append(f"{x:.1f},{y:.1f}")
    poly = " ".join(pts)
    return f'''\
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
  <rect x="0" y="0" width="{w}" height="{h}" fill="#fbfdff"/>
  <!-- axes -->
  <line x1="{cx0}" y1="20" x2="{cx0}" y2="{h-20}" stroke="#2e3440" stroke-width="1.5"/>
  <line x1="{cx0}" y1="{cy0}" x2="{cx0+plot_w+10}" y2="{cy0}" stroke="#2e3440" stroke-width="1.5"/>
  <polygon points="{cx0+plot_w+10},{cy0} {cx0+plot_w},{cy0-5} {cx0+plot_w},{cy0+5}" fill="#2e3440"/>
  <polygon points="{cx0},20 {cx0-5},30 {cx0+5},30" fill="#2e3440"/>
  <text x="{cx0+plot_w}" y="{cy0+20}" font-family="sans-serif" font-size="13" fill="#52606d">t</text>
  <text x="{cx0-18}" y="32" font-family="sans-serif" font-size="13" fill="#52606d">y</text>
  <!-- the wave -->
  <polyline points="{poly}" fill="none" stroke="{BLUE}" stroke-width="2.5"/>
  <!-- amplitude marker -->
  <line x1="{cx0+50}" y1="{cy0}" x2="{cx0+50}" y2="{cy0-amp}" stroke="{ORANGE}" stroke-width="1.5" stroke-dasharray="4 3"/>
  <text x="{cx0+56}" y="{cy0-amp/2}" font-family="sans-serif" font-size="12" fill="{ORANGE}">A</text>
  <!-- period marker -->
  <line x1="{cx0}" y1="{cy0+amp+18}" x2="{cx0+period_px}" y2="{cy0+amp+18}" stroke="{ORANGE}" stroke-width="1.5"/>
  <line x1="{cx0}" y1="{cy0+amp+12}" x2="{cx0}" y2="{cy0+amp+24}" stroke="{ORANGE}" stroke-width="1.5"/>
  <line x1="{cx0+period_px}" y1="{cy0+amp+12}" x2="{cx0+period_px}" y2="{cy0+amp+24}" stroke="{ORANGE}" stroke-width="1.5"/>
  <text x="{cx0+period_px/2}" y="{cy0+amp+36}" font-family="sans-serif" font-size="12" fill="{ORANGE}" text-anchor="middle">period T</text>
  <text x="{w/2}" y="24" font-family="sans-serif" font-size="17" font-weight="bold" fill="#2e3440" text-anchor="middle">y = A sin(2&#960;t / T)</text>
</svg>'''


WAVE_SVG = _wave_svg()


def _wave():
    return [
        _md("# Annotated Sine Wave\nA sine curve on arrowed axes with "
            "amplitude and period markers — the `<polyline>` points are "
            "computed in Python, then frozen into static SVG."),
        _svg(WAVE_SVG),
    ]


# -- Bonus: a flowchart with boxes + arrows --------------------------------

FLOWCHART_SVG = '''\
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 320 420" width="320" height="420">
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3"
            orient="auto" markerUnits="strokeWidth">
      <path d="M0 0 L8 3 L0 6 Z" fill="#2e3440"/>
    </marker>
  </defs>
  <rect x="0" y="0" width="320" height="420" fill="#f4f7fb"/>
  <!-- start -->
  <rect x="100" y="20" width="120" height="44" rx="22" fill="#3776ab"/>
  <text x="160" y="47" font-family="sans-serif" font-size="14" fill="#fff" text-anchor="middle">Start</text>
  <!-- process -->
  <rect x="90" y="104" width="140" height="50" rx="8" fill="#fff" stroke="#3776ab" stroke-width="2"/>
  <text x="160" y="134" font-family="sans-serif" font-size="13" fill="#2e3440" text-anchor="middle">Read input</text>
  <!-- decision -->
  <polygon points="160,194 230,238 160,282 90,238" fill="#fff" stroke="#e07b39" stroke-width="2"/>
  <text x="160" y="242" font-family="sans-serif" font-size="13" fill="#2e3440" text-anchor="middle">Valid?</text>
  <!-- yes process -->
  <rect x="90" y="322" width="140" height="50" rx="8" fill="#50bea0"/>
  <text x="160" y="352" font-family="sans-serif" font-size="13" fill="#fff" text-anchor="middle">Process</text>
  <!-- no return -->
  <text x="250" y="234" font-family="sans-serif" font-size="11" fill="#e07b39">no</text>
  <text x="166" y="312" font-family="sans-serif" font-size="11" fill="#2e7d4f">yes</text>
  <!-- connectors -->
  <line x1="160" y1="64"  x2="160" y2="100" stroke="#2e3440" stroke-width="2" marker-end="url(#arrow)"/>
  <line x1="160" y1="154" x2="160" y2="190" stroke="#2e3440" stroke-width="2" marker-end="url(#arrow)"/>
  <line x1="160" y1="282" x2="160" y2="318" stroke="#2e3440" stroke-width="2" marker-end="url(#arrow)"/>
  <!-- no path: right, up and back into "Read input" -->
  <path d="M230 238 H280 V129 H234" fill="none" stroke="#e07b39"
        stroke-width="2" marker-end="url(#arrow)"/>
</svg>'''


def _flowchart():
    return [
        _md("# Flowchart\nBoxes, a decision diamond and arrows with a "
            "`<marker>` arrowhead — a flowchart you can edit in place."),
        _svg(FLOWCHART_SVG),
    ]


# -- Registry --------------------------------------------------------------

SVG_EXAMPLES = [
    # (name, category, builder)
    ("Bohr Atom (SVG)",      "Drawing", _bohr_atom),
    ("Icon Grid (SVG)",      "Drawing", _icon_grid),
    ("Gradient Sunset (SVG)", "Drawing", _abstract),
    ("Bar Chart (SVG)",      "Drawing", _bar_chart),
    ("Tiling Pattern (SVG)", "Drawing", _tiling),
    ("Annotated Wave (SVG)", "Drawing", _wave),
    ("Flowchart (SVG)",      "Drawing", _flowchart),
]
