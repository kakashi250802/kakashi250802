#!/usr/bin/env python3
"""Renders every animated SVG shown in the kakashi250802 profile README.

    python3 scripts/profile_art.py static        # hand-designed art -> svg/
    python3 scripts/profile_art.py stats dist    # live stats from GitHub -> dist/

The `stats` command runs daily in GitHub Actions. Only the standard library is
used, so the job needs no setup step.
"""

import datetime
import html
import json
import math
import pathlib
import random
import re
import sys
import urllib.request

USER = "kakashi250802"

SANS = "'Segoe UI', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Ubuntu, Arial, sans-serif"
MONO = "'SF Mono', 'JetBrains Mono', Menlo, Consolas, 'Liberation Mono', monospace"

BG0, BG1 = "#070b1a", "#131b40"
CYAN, VIOLET, PINK, AMBER, GREEN = "#22d3ee", "#8b5cf6", "#ec4899", "#f59e0b", "#22c55e"
TEXT, MUTED, DIM = "#e2e8f0", "#94a3b8", "#64748b"

# Keyframes shared by several images.
BASE_CSS = (
    f"text{{font-family:{SANS}}}.mono{{font-family:{MONO}}}"
    "@keyframes dash{to{stroke-dashoffset:-1000}}"
    "@keyframes tw{0%,100%{opacity:.12}50%{opacity:.95}}"
    "@keyframes sweep{from{transform:translateX(-400px)}to{transform:translateX(1700px)}}"
    "@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}"
    ".tw{fill:#fff;animation:tw 3s ease-in-out infinite}"
)


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------


def esc(text):
    return html.escape(text, quote=True)


def svg(w, h, body, css="", label=""):
    """Wraps `body` in a standalone SVG document."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{esc(label)}">'
        f"<title>{esc(label)}</title><style>{BASE_CSS}{css}</style>{body}</svg>"
    )


def card(w, h, inner, uid, r=24, defs=""):
    """A rounded night-sky panel that clips its contents."""
    return (
        f'<defs><linearGradient id="{uid}bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{BG0}"/><stop offset="1" stop-color="{BG1}"/></linearGradient>'
        f'<clipPath id="{uid}clip"><rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="{r}"/></clipPath>'
        f"{defs}</defs>"
        f'<g clip-path="url(#{uid}clip)"><rect width="{w}" height="{h}" fill="url(#{uid}bg)"/>{inner}</g>'
        f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="{r}" fill="none" '
        'stroke="#fff" stroke-opacity=".08"/>'
    )


def border_light(w, h, r, c1, c2, uid, dur=6):
    """A comet of light that races around the card edge."""
    return (
        f'<defs><linearGradient id="{uid}bl" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient></defs>'
        f'<rect x="1.5" y="1.5" width="{w - 3}" height="{h - 3}" rx="{r}" fill="none" '
        f'stroke="url(#{uid}bl)" stroke-width="3" pathLength="1000" stroke-dasharray="200 800" '
        f'stroke-linecap="round" style="animation:dash {dur}s linear infinite"/>'
    )


def stars(rnd, count, w, h):
    out = []
    for _ in range(count):
        out.append(
            f'<circle cx="{rnd.uniform(0, w):.0f}" cy="{rnd.uniform(0, h):.0f}" '
            f'r="{rnd.choice([0.7, 1, 1.2, 1.6])}" class="tw" '
            f'style="animation-delay:{rnd.uniform(0, 4):.2f}s;animation-duration:{rnd.uniform(2.4, 5):.2f}s"/>'
        )
    return "".join(out)


def sweep(clip_id, h, dur=7, delay=0, opacity=0.10, width=160):
    """A diagonal sheen that glides across whatever `clip_id` outlines."""
    return (
        f'<g clip-path="url(#{clip_id})" style="pointer-events:none"><g transform="skewX(-24)">'
        f'<rect x="0" y="-20" width="{width}" height="{h + 40}" fill="#fff" opacity="{opacity}" '
        f'style="animation:sweep {dur}s ease-in-out {delay}s infinite"/></g></g>'
    )


def text_width(text, size, mono=False):
    return len(text) * size * (0.6 if mono else 0.56)


def pill(x, y, label, color):
    w = text_width(label, 13) + 24
    return (
        f'<rect x="{x}" y="{y}" width="{w:.0f}" height="26" rx="13" fill="{color}" fill-opacity=".14" '
        f'stroke="{color}" stroke-opacity=".55"/>'
        f'<text x="{x + w / 2:.0f}" y="{y + 17.5}" font-size="13" font-weight="600" fill="{color}" '
        f'text-anchor="middle">{esc(label)}</text>'
    ), w


def pills(x, y, labels, color):
    out = []
    for label in labels:
        part, w = pill(x, y, label, color)
        out.append(part)
        x += w + 8
    return "".join(out)


def wave(y, amp, period, w, h, fill, opacity, dur, reverse=False):
    pts = [f"M0 {h}"]
    for x in range(0, w + period + 1, 10):
        pts.append(f"L{x} {y + amp * math.sin(2 * math.pi * x / period):.1f}")
    pts.append(f"L{w + period} {h}Z")
    direction = "reverse" if reverse else "normal"
    return (
        f'<path d="{"".join(pts)}" fill="{fill}" opacity="{opacity}" '
        f'style="animation:wave{period} {dur}s linear infinite {direction}"/>'
    ), f"@keyframes wave{period}{{to{{transform:translateX(-{period}px)}}}}"


def odometer(x, y, value, size, color, begin=0.3, uid="o"):
    """Digits that roll into place like a mechanical counter."""
    line = size * 1.2
    cw = size * 0.6
    text = f"{value:,}"
    out = [
        f'<defs><clipPath id="{uid}"><rect x="{x - 4}" y="{y - size}" width="{cw * len(text) + 8:.0f}" '
        f'height="{line:.0f}"/></clipPath></defs><g clip-path="url(#{uid})" class="mono" '
        f'font-size="{size}" font-weight="800" fill="{color}">'
    ]
    for i, ch in enumerate(text):
        cx = x + i * cw
        if not ch.isdigit():
            out.append(f'<text x="{cx:.1f}" y="{y}" class="mono">{ch}</text>')
            continue
        seq = list(range(10)) + list(range(int(ch) + 1))
        travel = (len(seq) - 1) * line
        digits = "".join(
            f'<text x="{cx:.1f}" y="{y + k * line:.1f}" class="mono">{d}</text>' for k, d in enumerate(seq)
        )
        out.append(
            f'<g transform="translate(0 -{travel:.1f})">'
            f'<animateTransform attributeName="transform" type="translate" values="0 0;0 -{travel:.1f}" '
            f'dur="{1.6 + 0.18 * i:.2f}s" begin="{begin}s" fill="freeze" calcMode="spline" '
            f'keyTimes="0;1" keySplines=".15 .85 .25 1"/>{digits}</g>'
        )
    out.append("</g>")
    return "".join(out)


# --------------------------------------------------------------------------
# Hero
# --------------------------------------------------------------------------

ORBITS = [
    (92, 16, False, [("Rs", "#f97316"), ("Sw", "#f05138")]),
    (138, 24, True, [("Kt", "#a97bff"), ("TS", "#3b82f6"), ("RN", "#61dafb")]),
    (184, 34, False, [("GPU", "#f43f5e"), ("Py", "#facc15"), ("Ne", "#e0234e"), ("JS", "#fde047")]),
]


def orbit_system(cx, cy):
    out = [f'<g transform="translate({cx} {cy})">']
    for r, dur, rev, badges in ORBITS:
        spin, counter = ("360", "0") if not rev else ("0", "360")
        out.append(
            f'<circle r="{r}" fill="none" stroke="#fff" stroke-opacity=".09"/>'
            f'<circle r="{r}" fill="none" stroke="url(#ring)" stroke-width="2" pathLength="1000" '
            f'stroke-dasharray="90 910" style="animation:dash {dur / 2}s linear infinite"/>'
            f'<g><animateTransform attributeName="transform" type="rotate" from="{counter}" to="{spin}" '
            f'dur="{dur}s" repeatCount="indefinite"/>'
        )
        for i, (label, color) in enumerate(badges):
            a = 360 / len(badges) * i
            size = 12 if len(label) > 2 else 14
            out.append(
                f'<g transform="rotate({a:.0f}) translate({r} 0) rotate({-a:.0f})"><g>'
                f'<animateTransform attributeName="transform" type="rotate" from="{spin}" to="{counter}" '
                f'dur="{dur}s" repeatCount="indefinite" additive="sum"/>'
                f'<circle r="24" fill="{color}" opacity=".18"/>'
                f'<circle r="19" fill="#0a1029" stroke="{color}" stroke-width="2"/>'
                f'<text y="5" font-size="{size}" font-weight="800" fill="{color}" text-anchor="middle">{label}</text>'
                "</g></g>"
            )
        out.append("</g>")
    out.append(
        '<circle r="54" fill="url(#core)" opacity=".55"><animate attributeName="r" values="48;60;48" '
        'dur="4s" repeatCount="indefinite"/></circle>'
        f'<circle r="34" fill="#0a1029" stroke="{CYAN}" stroke-width="2"/>'
        '<text y="12" font-size="32" text-anchor="middle">🚀</text></g>'
    )
    return "".join(out)


ROLES = [
    "Rust & GPU rendering engines",
    "Native iOS (Swift) & Android (Kotlin)",
    "React Native & TypeScript apps",
    "Node.js, NestJS & Python backends",
]


def hero():
    w, h = 1200, 470
    rnd = random.Random(11)
    css = [
        "@keyframes a1{0%,100%{transform:translate(0,0)}50%{transform:translate(160px,50px)}}"
        "@keyframes a2{0%,100%{transform:translate(0,0)}50%{transform:translate(-140px,-30px)}}"
        "@keyframes a3{0%,100%{transform:translate(0,0)}50%{transform:translate(90px,-60px)}}"
        "@keyframes shoot{0%{transform:translateX(-300px);opacity:0}3%{opacity:1}"
        "16%{transform:translateX(1500px);opacity:0}100%{transform:translateX(1500px);opacity:0}}"
        "@keyframes role{0%{opacity:0;transform:translateY(16px)}4%,21%{opacity:1;transform:translateY(0)}"
        "25%,100%{opacity:0;transform:translateY(-16px)}}"
        "@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}"
        ".role{opacity:0;animation:role 12s ease-in-out infinite both}"
        ".cursor{animation:blink 1s step-end infinite}"
    ]
    waves = []
    for y, amp, period, fill, opacity, dur, rev in [
        (400, 14, 600, "url(#w1)", 0.55, 14, False),
        (418, 10, 400, "url(#w2)", 0.6, 9, True),
    ]:
        path, kf = wave(y, amp, period, w, h, fill, opacity, dur, rev)
        waves.append(path)
        css.append(kf)

    roles = "".join(
        f'<g class="role" style="animation-delay:{i * 3}s"><text x="80" y="300" font-size="27" '
        f'font-weight="600" fill="{TEXT}"><tspan fill="{CYAN}">❯ </tspan>{esc(role)}</text></g>'
        for i, role in enumerate(ROLES)
    )
    status = "Currently building Soar · a GPU UI engine in Rust"
    status_w = text_width(status, 15) + 52
    cmd = "$ cargo run -p soar-app"
    ok = "✓ ready"
    cmd_w = text_width(cmd + "  " + ok, 15, mono=True)

    defs = (
        f'<filter id="blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="55"/></filter>'
        f'<filter id="soft"><feGaussianBlur stdDeviation="10"/></filter>'
        f'<linearGradient id="name" gradientUnits="userSpaceOnUse" x1="80" y1="0" x2="480" y2="0" spreadMethod="repeat">'
        f'<stop offset="0" stop-color="{CYAN}"/><stop offset=".35" stop-color="{VIOLET}"/>'
        f'<stop offset=".7" stop-color="{PINK}"/><stop offset="1" stop-color="{CYAN}"/>'
        '<animateTransform attributeName="gradientTransform" type="translate" from="0 0" to="400 0" '
        'dur="5s" repeatCount="indefinite"/></linearGradient>'
        f'<linearGradient id="ring" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{CYAN}"/>'
        f'<stop offset="1" stop-color="{PINK}"/></linearGradient>'
        f'<radialGradient id="core"><stop offset="0" stop-color="{CYAN}"/><stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="w1" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{VIOLET}"/><stop offset="1" stop-color="{CYAN}"/></linearGradient>'
        f'<linearGradient id="w2" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{PINK}"/><stop offset="1" stop-color="{VIOLET}"/></linearGradient>'
        '<linearGradient id="trail" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset="1" stop-color="#fff"/></linearGradient>'
        f'<clipPath id="type"><rect x="100" y="340" width="0" height="40">'
        f'<animate attributeName="width" values="0;{cmd_w:.0f};{cmd_w:.0f};0" keyTimes="0;.35;.85;1" '
        'dur="7s" repeatCount="indefinite"/></rect></clipPath>'
    )
    inner = (
        f'<g filter="url(#blur)" opacity=".55">'
        f'<ellipse cx="260" cy="90" rx="260" ry="120" fill="{VIOLET}" style="animation:a1 14s ease-in-out infinite"/>'
        f'<ellipse cx="900" cy="330" rx="280" ry="130" fill="{CYAN}" opacity=".7" style="animation:a2 17s ease-in-out infinite"/>'
        f'<ellipse cx="640" cy="40" rx="200" ry="90" fill="{PINK}" opacity=".6" style="animation:a3 12s ease-in-out infinite"/></g>'
        f"{stars(rnd, 80, w, h - 80)}"
        '<g transform="translate(0 40) rotate(13)"><line x1="0" y1="0" x2="160" y2="0" stroke="url(#trail)" '
        'stroke-width="2" stroke-linecap="round" style="animation:shoot 8s ease-in 1s infinite"/></g>'
        # Status pill with a pulsing live dot.
        f'<rect x="80" y="58" width="{status_w:.0f}" height="36" rx="18" fill="#fff" fill-opacity=".06" '
        'stroke="#fff" stroke-opacity=".14"/>'
        f'<circle cx="101" cy="76" r="5" fill="{GREEN}"/><circle cx="101" cy="76" r="5" fill="none" stroke="{GREEN}">'
        '<animate attributeName="r" values="5;15" dur="1.8s" repeatCount="indefinite"/>'
        '<animate attributeName="opacity" values=".9;0" dur="1.8s" repeatCount="indefinite"/></circle>'
        f'<text x="118" y="81" font-size="15" fill="#cbd5e1">{esc(status)}</text>'
        f'<text x="80" y="150" font-size="24" fill="{MUTED}">Xin chào 👋 mình là</text>'
        '<text x="80" y="238" font-size="92" font-weight="800" fill="url(#name)" filter="url(#soft)" opacity=".55">duonnn</text>'
        '<text x="80" y="238" font-size="92" font-weight="800" fill="url(#name)">duonnn</text>'
        f"{roles}"
        # Terminal line that types itself, waits and erases.
        f'<rect x="80" y="335" width="{cmd_w + 60:.0f}" height="46" rx="12" fill="#050817" fill-opacity=".75" '
        'stroke="#fff" stroke-opacity=".1"/>'
        f'<g clip-path="url(#type)"><text x="100" y="364" font-size="15" class="mono" fill="{TEXT}">'
        f'{esc(cmd)}  <tspan fill="{GREEN}">{ok}</tspan></text></g>'
        f'<rect x="{100 + cmd_w + 6:.0f}" y="350" width="9" height="19" fill="{CYAN}" class="cursor"/>'
        f"{orbit_system(940, 210)}"
        f'{"".join(waves)}'
    )
    return svg(w, h, card(w, h, inner, "h", r=28, defs=defs), "".join(css), "duonnn - developer from Viet Nam")


# --------------------------------------------------------------------------
# About: a terminal that types its own introduction
# --------------------------------------------------------------------------

ABOUT = [
    ("cmd", "whoami"),
    ("out", "duonnn · developer from Việt Nam", TEXT),
    ("cmd", "cat now.md"),
    ("out", "🚀  Building Soar, a GPU-native mobile UI engine written in Rust", "#fdba74"),
    ("out", "🧩  Bridging Rust to Swift and Kotlin for iOS and Android", "#93c5fd"),
    ("out", "📱  Shipping cross-platform apps with React Native and TypeScript", "#67e8f9"),
    ("cmd", "echo $MOTTO"),
    ("out", '"Why flutter when you can soar?"', "#f0abfc"),
]


def about():
    w = 1200
    line_h, top = 30, 92
    h = top + line_h * (len(ABOUT) + 1) + 18
    t = 0.4
    defs, body = [], []
    for i, item in enumerate(ABOUT):
        y = top + i * line_h
        if item[0] == "cmd":
            typed = text_width(item[1], 17, mono=True)
            dur = 0.07 * len(item[1]) + 0.2
            defs.append(
                f'<clipPath id="t{i}"><rect x="78" y="{y - 22}" width="0" height="30">'
                f'<animate attributeName="width" from="0" to="{typed + 40:.0f}" begin="{t:.2f}s" '
                f'dur="{dur:.2f}s" fill="freeze"/></rect></clipPath>'
            )
            body.append(
                f'<g clip-path="url(#t{i})"><text x="80" y="{y}" font-size="17" class="mono">'
                f'<tspan fill="{GREEN}">❯</tspan> <tspan fill="{TEXT}">{esc(item[1])}</tspan></text></g>'
            )
            t += dur + 0.25
        else:
            body.append(
                f'<text x="104" y="{y}" font-size="17" class="mono" fill="{item[2]}" opacity="0">{esc(item[1])}'
                f'<animate attributeName="opacity" from="0" to="1" begin="{t:.2f}s" dur=".35s" fill="freeze"/></text>'
            )
            t += 0.35
    y = top + len(ABOUT) * line_h
    body.append(
        f'<text x="80" y="{y}" font-size="17" class="mono" fill="{GREEN}" opacity="0">❯'
        f'<animate attributeName="opacity" from="0" to="1" begin="{t:.2f}s" dur=".2s" fill="freeze"/></text>'
        f'<rect x="102" y="{y - 16}" width="10" height="20" fill="{CYAN}" opacity="0">'
        f'<animate attributeName="opacity" values="1;0" dur="1s" begin="{t:.2f}s" repeatCount="indefinite" calcMode="discrete"/></rect>'
    )
    chrome = (
        '<rect width="1200" height="48" fill="#fff" fill-opacity=".04"/>'
        '<line x1="0" y1="48" x2="1200" y2="48" stroke="#fff" stroke-opacity=".08"/>'
        '<circle cx="30" cy="24" r="7" fill="#ff5f57"/><circle cx="54" cy="24" r="7" fill="#febc2e"/>'
        '<circle cx="78" cy="24" r="7" fill="#28c840"/>'
        f'<text x="600" y="29" font-size="14" fill="{DIM}" text-anchor="middle" class="mono">duonnn@soar: ~</text>'
        f'<text x="1170" y="29" font-size="13" fill="{DIM}" text-anchor="end">about me</text>'
    )
    inner = chrome + "".join(body) + border_light(w, h, 20, CYAN, VIOLET, "ab", 9)
    return svg(w, h, card(w, h, inner, "a", r=20, defs="".join(defs)), "", "About duonnn")


# --------------------------------------------------------------------------
# Stack: a periodic table of the tools in daily use
# --------------------------------------------------------------------------

STACK = [
    ("Systems & GPU", "#fb923c", [
        ("Rs", "Rust", "engine core"), ("Wg", "wgpu", "GPU API"), ("Ws", "WGSL", "shaders"),
        ("Mt", "Metal", "Apple GPU"), ("Vk", "Vulkan", "Android GPU"), ("Vm", "Bytecode VM", "runtime"),
    ]),
    ("Native mobile", "#60a5fa", [
        ("Sw", "Swift", "iOS host"), ("Kt", "Kotlin", "Android host"), ("iO", "iOS", "UIKit"),
        ("An", "Android", "NDK"), ("Jn", "JNI", "FFI bridge"),
    ]),
    ("Apps & web", CYAN, [
        ("Ts", "TypeScript", "everywhere"), ("Tx", "TSX", "UI language"), ("Rn", "React Native", "mobile apps"),
        ("Re", "React", "web UI"), ("Nx", "Next.js", "web apps"), ("Vu", "Vue", "web UI"),
    ]),
    ("Backend & data", "#34d399", [
        ("Nd", "Node.js", "runtime"), ("Ne", "NestJS", "APIs"), ("Py", "Python", "scripts"),
        ("Mg", "MongoDB", "database"), ("Fb", "Firebase", "realtime"),
    ]),
    ("Tools & AI", "#c084fc", [
        ("Gt", "Git", "versioning"), ("Gh", "Actions", "CI/CD"), ("Xc", "Xcode", "iOS builds"),
        ("As", "Android Studio", "Android builds"), ("Vs", "VS Code", "editor"), ("Cc", "Claude Code", "AI pair"),
    ]),
]


def stack():
    w = 1200
    tile_w, tile_h, gap = 142, 112, 12
    top, left = 130, 262
    h = top + len(STACK) * (tile_h + gap) + 26
    css = (
        "@keyframes pop{from{opacity:0;transform:translateY(18px) scale(.9)}to{opacity:1;transform:none}}"
        "@keyframes edge{0%,100%{stroke-opacity:.35}50%{stroke-opacity:.95}}"
        ".tile{transform-box:fill-box;transform-origin:center;animation:pop .7s cubic-bezier(.2,.9,.3,1.25) both}"
        ".edge{animation:edge 4s ease-in-out infinite}"
    )
    clip, tiles, labels = [], [], []
    number = 0
    for row, (category, color, items) in enumerate(STACK):
        y = top + row * (tile_h + gap)
        labels.append(
            f'<rect x="40" y="{y + 28}" width="4" height="56" rx="2" fill="{color}"/>'
            f'<text x="58" y="{y + 52}" font-size="18" font-weight="700" fill="{color}">{esc(category)}</text>'
            f'<text x="58" y="{y + 76}" font-size="13" fill="{DIM}">{len(items)} elements</text>'
        )
        for col, (sym, name, tag) in enumerate(items):
            number += 1
            x = left + col * (tile_w + gap)
            delay = (row * 6 + col) * 0.05
            clip.append(f'<rect x="{x}" y="{y}" width="{tile_w}" height="{tile_h}" rx="14"/>')
            name_size = 14 if len(name) < 13 else 12
            tiles.append(
                f'<g class="tile" style="animation-delay:{delay:.2f}s">'
                f'<rect x="{x}" y="{y}" width="{tile_w}" height="{tile_h}" rx="14" fill="url(#tile{row})"/>'
                f'<rect x="{x + .5}" y="{y + .5}" width="{tile_w - 1}" height="{tile_h - 1}" rx="14" fill="none" '
                f'stroke="{color}" class="edge" style="animation-delay:{delay * 3:.2f}s"/>'
                f'<text x="{x + 12}" y="{y + 22}" font-size="12" fill="{DIM}" class="mono">{number:02d}</text>'
                f'<text x="{x + tile_w - 12}" y="{y + 22}" font-size="11" fill="{DIM}" text-anchor="end">{esc(tag)}</text>'
                f'<text x="{x + 12}" y="{y + 66}" font-size="36" font-weight="800" fill="{color}">{esc(sym)}</text>'
                f'<text x="{x + 12}" y="{y + 94}" font-size="{name_size}" font-weight="600" fill="{TEXT}">{esc(name)}</text>'
                "</g>"
            )
    grads = "".join(
        f'<linearGradient id="tile{i}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{c}" stop-opacity=".22"/>'
        f'<stop offset=".6" stop-color="#0b1230" stop-opacity=".9"/></linearGradient>'
        for i, (_, c, _) in enumerate(STACK)
    )
    defs = f'{grads}<clipPath id="tiles">{"".join(clip)}</clipPath>'
    rnd = random.Random(5)
    header = (
        f'<text x="40" y="66" font-size="32" font-weight="800" fill="{TEXT}">The elements I build with</text>'
        f'<text x="40" y="96" font-size="16" fill="{MUTED}">My current stack, from GPU shaders down to the backend.</text>'
        f'<text x="1160" y="66" font-size="14" fill="{DIM}" text-anchor="end" class="mono">{number} elements · 5 groups</text>'
    )
    inner = stars(rnd, 40, w, h) + header + "".join(labels) + "".join(tiles) + sweep("tiles", h, dur=6, opacity=0.09, width=220)
    return svg(w, h, card(w, h, inner, "s", defs=defs), css, "My tech stack")


# --------------------------------------------------------------------------
# Projects
# --------------------------------------------------------------------------

PIPELINE = [("TSX", CYAN), ("Bytecode VM", VIOLET), ("Layout", "#60a5fa"), ("Renderer", PINK), ("GPU", "#fb923c")]


def soar_card():
    w, h = 1200, 380
    css = ".float{animation:bob 4s ease-in-out infinite}"
    desc = [
        "A mobile UI engine with a Rust core. It draws every pixel itself",
        "on the GPU, runs app logic written in TSX on a verified bytecode",
        "VM, and ships updates over the air as data.",
    ]
    lines = "".join(
        f'<text x="60" y="{214 + i * 26}" font-size="17" fill="#cbd5e1">{esc(t)}</text>' for i, t in enumerate(desc)
    )
    # Pipeline: nodes on a zigzag with packets of data flowing along it.
    xs = [700, 815, 930, 1045, 1140]
    ys = [190, 270, 190, 270, 190]
    path = "M" + " L".join(f"{x} {y}" for x, y in zip(xs, ys))
    nodes = []
    for i, ((label, color), x, y) in enumerate(zip(PIPELINE, xs, ys)):
        bw = max(76, text_width(label, 14) + 26)
        nodes.append(
            f'<g class="float" style="animation-delay:{i * .4}s">'
            f'<rect x="{x - bw / 2:.0f}" y="{y - 20}" width="{bw:.0f}" height="40" rx="12" fill="#0a1029" '
            f'stroke="{color}" stroke-width="2"/><rect x="{x - bw / 2:.0f}" y="{y - 20}" width="{bw:.0f}" height="40" '
            f'rx="12" fill="{color}" opacity=".12"/>'
            f'<text x="{x}" y="{y + 5}" font-size="14" font-weight="700" fill="{color}" text-anchor="middle">{label}</text></g>'
        )
    packets = "".join(
        f'<circle r="5" fill="{c}"><animateMotion dur="4s" begin="{i * .8}s" repeatCount="indefinite" path="{path}"/></circle>'
        f'<circle r="11" fill="{c}" opacity=".25"><animateMotion dur="4s" begin="{i * .8}s" repeatCount="indefinite" path="{path}"/></circle>'
        for i, c in enumerate([CYAN, VIOLET, PINK, "#fb923c", "#60a5fa"])
    )
    defs = (
        f'<linearGradient id="title" gradientUnits="userSpaceOnUse" x1="60" x2="360" spreadMethod="repeat">'
        f'<stop offset="0" stop-color="#fb923c"/><stop offset=".5" stop-color="{PINK}"/><stop offset="1" stop-color="#fb923c"/>'
        '<animateTransform attributeName="gradientTransform" type="translate" from="0 0" to="300 0" dur="4s" repeatCount="indefinite"/>'
        "</linearGradient>"
    )
    rnd = random.Random(3)
    inner = (
        stars(rnd, 50, w, h)
        + f'<text x="40" y="62" font-size="30" font-weight="800" fill="{TEXT}">Things I’m building</text>'
        + f'<line x1="40" y1="84" x2="1160" y2="84" stroke="#fff" stroke-opacity=".08"/>'
        + f'<rect x="60" y="108" width="200" height="28" rx="14" fill="{AMBER}" fill-opacity=".15" stroke="{AMBER}" stroke-opacity=".6"/>'
        + f'<text x="160" y="127" font-size="13" font-weight="700" fill="{AMBER}" text-anchor="middle" letter-spacing="1">FEATURED · IN PROGRESS</text>'
        + '<text x="60" y="184" font-size="48" font-weight="800" fill="url(#title)">Soar</text>'
        + f'<text x="190" y="182" font-size="18" font-style="italic" fill="{MUTED}">Why flutter when you can soar?</text>'
        + lines
        + pills(60, 310, ["Rust", "wgpu", "Swift", "Kotlin", "TSX"], "#fb923c")
        + f'<path d="{path}" fill="none" stroke="#fff" stroke-opacity=".15" stroke-width="2" stroke-dasharray="6 8"/>'
        + packets
        + "".join(nodes)
        + f'<text x="920" y="340" font-size="13" fill="{DIM}" text-anchor="middle">from TSX to pixels, all drawn by Soar</text>'
        + border_light(w, h, 24, "#fb923c", PINK, "sb", 7)
    )
    return svg(w, h, card(w, h, inner, "p", defs=defs), css, "Soar - a GPU-native mobile UI engine")


PROJECTS = [
    ("sleep-tracker-backend", "😴", "#34d399", ["REST backend for a sleep tracking app,", "built with NestJS and TypeScript."], ["NestJS", "TypeScript"]),
    ("tiktokserver", "🔎", "#f472b6", ["Fetches public TikTok profile stats by", "username or ID, no login or API key."], ["Python", "Scraping"]),
    ("SlackClone", "💬", "#a78bfa", ["A Slack-style team chat built with", "React, Redux Toolkit and Firebase."], ["React", "Redux", "Firebase"]),
    ("spotifyclone", "🎵", "#4ade80", ["A Spotify-style music player UI built", "with Next.js and Tailwind CSS."], ["Next.js", "Tailwind"]),
]


def project_card(name, icon, color, desc, tags, index):
    w, h = 590, 210
    css = ".float{animation:bob 3.5s ease-in-out infinite}"
    inner = (
        f'<circle cx="520" cy="40" r="90" fill="{color}" opacity=".10"/>'
        f'<g class="float" style="animation-delay:{index * .5}s">'
        f'<rect x="32" y="32" width="60" height="60" rx="16" fill="{color}" fill-opacity=".15" stroke="{color}" stroke-opacity=".6"/>'
        f'<text x="62" y="72" font-size="28" text-anchor="middle">{icon}</text></g>'
        f'<text x="110" y="58" font-size="22" font-weight="800" fill="{TEXT}">{esc(name)}</text>'
        f'<text x="110" y="82" font-size="13" fill="{DIM}" class="mono">github.com/{USER}/{esc(name)}</text>'
        + "".join(f'<text x="32" y="{126 + i * 22}" font-size="15" fill="#cbd5e1">{esc(t)}</text>' for i, t in enumerate(desc))
        + pills(32, 164, tags, color)
        + f'<text x="558" y="182" font-size="20" fill="{color}" text-anchor="end">↗</text>'
        + border_light(w, h, 20, color, VIOLET, f"pc{index}", 5 + index)
    )
    return svg(w, h, card(w, h, inner, f"c{index}", r=20), css, name)


# --------------------------------------------------------------------------
# Contact
# --------------------------------------------------------------------------

BUTTONS = [
    ("email", "Email me", "#ea4335", "#f97316"),
    ("facebook", "Facebook", "#1877f2", "#60a5fa"),
    ("instagram", "Instagram", "#d946ef", "#f59e0b"),
]


def button_icon(kind):
    if kind == "email":
        return (
            '<rect x="24" y="22" width="26" height="20" rx="3" fill="none" stroke="#fff" stroke-width="2.4"/>'
            '<path d="M25 24 L37 34 L49 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linejoin="round"/>'
        )
    if kind == "facebook":
        return '<text x="37" y="43" font-size="28" font-weight="800" fill="#fff" text-anchor="middle">f</text>'
    return (
        '<rect x="24" y="19" width="26" height="26" rx="8" fill="none" stroke="#fff" stroke-width="2.4"/>'
        '<circle cx="37" cy="32" r="6" fill="none" stroke="#fff" stroke-width="2.4"/>'
        '<circle cx="44.5" cy="24.5" r="1.8" fill="#fff"/>'
    )


def button(kind, label, c1, c2, index):
    w, h = 250, 64
    defs = (
        f'<linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{c1}"/>'
        f'<stop offset="1" stop-color="{c2}"/></linearGradient>'
        f'<clipPath id="b"><rect width="{w}" height="{h}" rx="32"/></clipPath>'
    )
    body = (
        f"<defs>{defs}</defs>"
        f'<rect width="{w}" height="{h}" rx="32" fill="url(#g)"/>'
        f'<rect x="1" y="1" width="{w - 2}" height="{h / 2}" rx="31" fill="#fff" opacity=".12"/>'
        f"{button_icon(kind)}"
        f'<text x="66" y="40" font-size="20" font-weight="700" fill="#fff">{esc(label)}</text>'
        f'<text x="222" y="40" font-size="20" fill="#fff" text-anchor="middle">→</text>'
        + sweep("b", h, dur=4, delay=index * 0.6, opacity=0.35, width=50)
    )
    return svg(w, h, body, "", label)


def connect_header():
    w, h = 1200, 140
    rnd = random.Random(9)
    css = "@keyframes spark{0%,100%{transform:scale(.6) rotate(0);opacity:.3}50%{transform:scale(1.2) rotate(90deg);opacity:1}}.sp{transform-box:fill-box;transform-origin:center;animation:spark 3s ease-in-out infinite}"
    sparks = "".join(
        f'<path class="sp" style="animation-delay:{i * .5}s" d="M{x} {y - 9} L{x + 2.5} {y - 2.5} L{x + 9} {y} L{x + 2.5} {y + 2.5} '
        f'L{x} {y + 9} L{x - 2.5} {y + 2.5} L{x - 9} {y} L{x - 2.5} {y - 2.5}Z" fill="{c}"/>'
        for i, (x, y, c) in enumerate([(300, 50, CYAN), (900, 44, PINK), (240, 100, VIOLET), (965, 98, AMBER), (600, 22, TEXT)])
    )
    inner = (
        stars(rnd, 50, w, h)
        + sparks
        + '<text x="600" y="72" font-size="34" font-weight="800" fill="url(#hg)" text-anchor="middle">Let’s build something together</text>'
        + f'<text x="600" y="106" font-size="16" fill="{MUTED}" text-anchor="middle">Questions, ideas or just a hello. My inbox is always open.</text>'
    )
    defs = (
        f'<linearGradient id="hg" gradientUnits="userSpaceOnUse" x1="350" x2="850" spreadMethod="repeat">'
        f'<stop offset="0" stop-color="{CYAN}"/><stop offset=".5" stop-color="{PINK}"/><stop offset="1" stop-color="{CYAN}"/>'
        '<animateTransform attributeName="gradientTransform" type="translate" from="0 0" to="500 0" dur="5s" repeatCount="indefinite"/>'
        "</linearGradient>"
    )
    return svg(w, h, card(w, h, inner, "ch", defs=defs), css, "Let's build something together")


def footer():
    w, h = 1200, 120
    css, parts = [], []
    for y, amp, period, fill, op, dur, rev in [
        (40, 16, 600, "url(#f1)", 0.5, 12, False),
        (58, 12, 400, "url(#f2)", 0.6, 8, True),
        (76, 8, 300, "url(#f1)", 0.9, 6, False),
    ]:
        path, kf = wave(y, amp, period, w, h, fill, op, dur, rev)
        parts.append(path)
        css.append(kf)
    defs = (
        f'<defs><linearGradient id="f1" x1="0" x2="1"><stop offset="0" stop-color="{CYAN}"/><stop offset=".5" stop-color="{VIOLET}"/>'
        f'<stop offset="1" stop-color="{PINK}"/></linearGradient>'
        f'<linearGradient id="f2" x1="0" x2="1"><stop offset="0" stop-color="{PINK}"/><stop offset="1" stop-color="{CYAN}"/></linearGradient></defs>'
    )
    body = defs + "".join(parts) + '<text x="600" y="108" font-size="13" fill="#fff" fill-opacity=".85" text-anchor="middle">thanks for stopping by ✦ see you in the sky</text>'
    return svg(w, h, body, "".join(css), "")


# --------------------------------------------------------------------------
# Live stats (run daily by GitHub Actions)
# --------------------------------------------------------------------------


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": f"{USER}-profile-art"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def contributions():
    """Reads the public contribution calendar: total and one count per day."""
    page = fetch(f"https://github.com/users/{USER}/contributions")
    total = int(re.search(r"([\d,]+)\s+contributions?\s+in the last year", page).group(1).replace(",", ""))
    counts = {}
    for tip_for, tip in re.findall(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]*)', page):
        m = re.match(r"\s*(\d+|No) contributions?", tip)
        counts[tip_for] = 0 if not m or m.group(1) == "No" else int(m.group(1))
    days = []
    for attrs in re.findall(r"<td([^>]*ContributionCalendar-day[^>]*)>", page):
        date = re.search(r'data-date="([^"]+)"', attrs)
        ident = re.search(r'id="([^"]+)"', attrs)
        level = re.search(r'data-level="(\d)"', attrs)
        if date and ident and level:
            days.append((date.group(1), counts.get(ident.group(1), 0), int(level.group(1))))
    days.sort()
    return total, days


def streaks(days):
    today = datetime.date.today().isoformat()
    counts = [c for d, c, _ in days if d <= today]
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    current = 0
    tail = counts[:-1] if counts and counts[-1] == 0 else counts
    for c in reversed(tail):
        if not c:
            break
        current += 1
    return current, longest


def stats_card(total, days, repos):
    w, h = 1200, 250
    current, longest = streaks(days)
    best = max((c for _, c, _ in days), default=0)
    tiles = [
        ("Contributions", total, "in the last year", CYAN),
        ("Current streak", current, "days in a row", "#fb923c"),
        ("Longest streak", longest, "days this year", PINK),
        ("Best day", best, f"contributions · {repos} public repos", VIOLET),
    ]
    body = []
    for i, (label, value, note, color) in enumerate(tiles):
        x = 40 + i * 285
        body.append(
            f'<rect x="{x}" y="96" width="265" height="124" rx="18" fill="{color}" fill-opacity=".08" stroke="{color}" stroke-opacity=".35"/>'
            f'<text x="{x + 22}" y="128" font-size="14" font-weight="600" fill="{color}" letter-spacing=".5">{label.upper()}</text>'
            + odometer(x + 22, 180, value, 44, TEXT, begin=0.3 + i * 0.25, uid=f"od{i}")
            + f'<text x="{x + 22}" y="204" font-size="13" fill="{DIM}">{esc(note)}</text>'
        )
    updated = datetime.date.today().strftime("%d %b %Y")
    header = (
        f'<text x="40" y="62" font-size="30" font-weight="800" fill="{TEXT}">Live stats</text>'
        f'<circle cx="190" cy="52" r="5" fill="{GREEN}"><animate attributeName="opacity" values="1;.2;1" dur="1.6s" repeatCount="indefinite"/></circle>'
        f'<text x="1160" y="62" font-size="13" fill="{DIM}" text-anchor="end" class="mono">updated {updated}</text>'
    )
    rnd = random.Random(2)
    inner = stars(rnd, 40, w, h) + header + "".join(body)
    return svg(w, h, card(w, h, inner, "st"), "", "Live GitHub stats")


LEVELS = ["#151c3b", "#164e63", "#0891b2", "#22d3ee", "#a5f3fc"]


def activity_card(total, days):
    w, h = 1200, 290
    cell, gap = 15, 4
    weeks = math.ceil(len(days) / 7) if days else 53
    grid_w = weeks * (cell + gap) - gap
    x0, y0 = (w - grid_w) // 2 + 14, 110
    css = (
        "@keyframes cell{from{opacity:0;transform:scale(.2)}to{opacity:1;transform:none}}"
        ".c{transform-box:fill-box;transform-origin:center;animation:cell .45s ease-out both}"
    )
    cells, clip, months = [], [], []
    first = datetime.date.fromisoformat(days[0][0]) if days else datetime.date.today()
    offset = (first.weekday() + 1) % 7  # GitHub weeks start on Sunday.
    seen = set()
    for i, (date, count, level) in enumerate(days):
        slot = i + offset
        col, row = divmod(slot, 7)
        x, y = x0 + col * (cell + gap), y0 + row * (cell + gap)
        cells.append(
            f'<rect class="c" style="animation-delay:{col * .025:.3f}s" x="{x}" y="{y}" width="{cell}" height="{cell}" '
            f'rx="4" fill="{LEVELS[level]}"><title>{count} on {date}</title></rect>'
        )
        if level:
            clip.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="4"/>')
        month = date[:7]
        if date[8:] <= "07" and month not in seen and row == 0:
            seen.add(month)
            label = datetime.date.fromisoformat(date).strftime("%b")
            months.append(f'<text x="{x}" y="{y0 - 12}" font-size="12" fill="{DIM}">{label}</text>')
    for row, label in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        months.append(f'<text x="{x0 - 10}" y="{y0 + row * (cell + gap) + 12}" font-size="11" fill="{DIM}" text-anchor="end">{label}</text>')
    legend_x = x0 + grid_w - 5 * (cell + gap) + gap
    legend = (
        f'<text x="{legend_x - 10}" y="{y0 + 7 * (cell + gap) + 26}" font-size="12" fill="{DIM}" text-anchor="end">Less</text>'
        + "".join(
            f'<rect x="{legend_x + i * (cell + gap)}" y="{y0 + 7 * (cell + gap) + 14}" width="{cell}" height="{cell}" rx="4" fill="{c}"/>'
            for i, c in enumerate(LEVELS)
        )
        + f'<text x="{legend_x + 5 * (cell + gap) + 4}" y="{y0 + 7 * (cell + gap) + 26}" font-size="12" fill="{DIM}">More</text>'
    )
    header = (
        f'<text x="40" y="62" font-size="30" font-weight="800" fill="{TEXT}">A year of building</text>'
        f'<text x="1160" y="62" font-size="16" fill="{MUTED}" text-anchor="end">'
        f'<tspan fill="{CYAN}" font-weight="700">{total:,}</tspan> contributions in the last year</text>'
    )
    defs = f'<clipPath id="lit">{"".join(clip)}</clipPath>'
    inner = header + "".join(months) + "".join(cells) + legend + sweep("lit", h, dur=5, delay=1.5, opacity=0.55, width=60)
    return svg(w, h, card(w, h, inner, "ac", defs=defs), css, f"{total} contributions in the last year")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def write(path, content):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path} ({len(content) / 1024:.1f} KB)")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("static", "stats"):
        sys.exit(__doc__)
    root = pathlib.Path(__file__).resolve().parent.parent
    if sys.argv[1] == "static":
        out = root / "svg"
        write(out / "hero.svg", hero())
        write(out / "about.svg", about())
        write(out / "stack.svg", stack())
        write(out / "projects" / "soar.svg", soar_card())
        for i, project in enumerate(PROJECTS):
            write(out / "projects" / f"{project[0]}.svg", project_card(*project, i))
        write(out / "connect.svg", connect_header())
        for i, (kind, label, c1, c2) in enumerate(BUTTONS):
            write(out / "buttons" / f"{kind}.svg", button(kind, label, c1, c2, i))
        write(out / "footer.svg", footer())
        return
    out = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "dist")
    total, days = contributions()
    repos = json.loads(fetch(f"https://api.github.com/users/{USER}"))["public_repos"]
    write(out / "stats.svg", stats_card(total, days, repos))
    write(out / "activity.svg", activity_card(total, days))


if __name__ == "__main__":
    main()
