#!/usr/bin/env python3
"""
check-brand-sync.py — fail if the website's palette or type has drifted from the app's.

WHY THIS EXISTS
---------------
On 2026-07-25 a cross-reference found colors_and_type.css carrying the pre-1.20
palette (bg #1A0E2E, gold #E8B560) while the shipping app had long since moved to
#07040E and #EDA040 — and the stylesheet header still claimed "Source:
MeringoColors.kt (verified against codebase)". The type had drifted too: the site
served Outfit + JetBrains Mono, the app ships Inter + Share Tech Mono.

It was visible on the page. index.html embeds real app screenshots, so the hero's
gold proof-chip sat next to a phone photo whose pause button was a different gold.
Nobody caught it for two months, because the app has a docs-in-sync rule binding
the Field Guide and Full Manual, and NOTHING bound this repo to the app at all.

This script is that binding. It reads the app's MeringoColors.kt as the source of
truth and diffs it against the CSS custom properties that claim to mirror it.

USAGE
-----
    python tools/check-brand-sync.py                      # assumes ../meringo
    python tools/check-brand-sync.py --app-repo D:/src/meringo
    python tools/check-brand-sync.py --quiet              # only print on failure

Exit 0 = in sync. Exit 1 = drift (prints a table). Exit 2 = couldn't run the check
(app repo not found, files moved). Exit 2 is NOT a pass — it means unverified.

The app is always the source of truth: it ships, and its tokens are graded for
contrast in docs/A11Y_CONTRAST_AUDIT.md. If this fails, the fix is normally to
update the website, not the app.
"""

import argparse
import os
import re
import sys

# CSS custom property  ->  the `val <Name>` in MeringoColors.kt it must equal.
# Several CSS vars intentionally alias one Kotlin token (e.g. --color-void and
# --color-bg-base are both MidnightVelvet); each alias is checked independently so
# a partial find-and-replace can't leave one behind.
COLOR_MAP = {
    "--color-midnight-velvet": "MidnightVelvet",
    "--color-void":            "MidnightVelvet",
    "--color-bg-base":         "MidnightVelvet",
    "--color-velvet-surface":  "VelvetSurface",
    "--color-bg-surface":      "VelvetSurface",
    "--color-velvet-elevated": "VelvetElevated",
    "--color-bg-elevated":     "VelvetElevated",
    "--color-velvet-highest":  "VelvetPeak",
    "--color-bg-overlay":      "VelvetPeak",
    "--color-border-dim":      "VelvetBorder",
    "--color-gold":            "CandlelightGold",
    "--color-gold-dim":        "CandlelightDim",
    "--color-border-bright":   "CandlelightDim",
    "--color-text-0":          "Parchment",
    "--color-text-1":          "ParchmentDim",
    "--color-text-2":          "ParchmentFaint",
    "--color-border-default":  "ParchmentFaint",
    "--color-teal":            "RuneTeal",
    "--color-teal-dim":        "RuneTealDim",
    "--color-teal-bright":     "RuneTealBright",
    "--color-audiophile-gold": "AudiophileGold",
    "--color-success":         "SuccessGreen",
    "--color-warning":         "WarningAmber",
    "--color-error":           "EmberRed",
}

# Font families the app bundles in core/design/src/main/res/font/, mapped to the
# family name the CSS must name FIRST in its stack. Deliberately not a full
# @font-face audit — this catches "the site switched families", which is the
# failure that actually happened.
FONT_MAP = {
    "--font-display": "Cormorant Garamond",
    "--font-ui":      "Inter",
    "--font-mono":    "Share Tech Mono",
}

# Tokens with no CSS counterpart, listed so this file documents the decision
# rather than silently ignoring them.
INTENTIONALLY_UNMAPPED = {
    "CandlelightContainer",  # tonal button fill — no web equivalent
    "ParchmentDisabled",     # pre-composited OFF-state text, app-only pattern
    "VelvetShadow",          # equals MidnightVelvet; web uses rgba() shadows
    "NixieTubeOrange",       # NixieReadout component, app-only
}


def die(msg, code=2):
    print(f"check-brand-sync: {msg}", file=sys.stderr)
    sys.exit(code)


def parse_kotlin_colors(path):
    """`val CandlelightGold = Color(0xFFEDA040)` -> {'CandlelightGold': '#EDA040'}

    Handles both 0xRRGGBB and 0xAARRGGBB; alpha is dropped, since the CSS side
    carries opacity separately via rgba()."""
    try:
        src = open(path, encoding="utf-8").read()
    except OSError as e:
        die(f"cannot read app colors at {path}: {e}")
    out = {}
    for m in re.finditer(r"^val\s+(\w+)\s*=\s*Color\(0x([0-9A-Fa-f]{6,8})\)", src, re.M):
        name, hexv = m.group(1), m.group(2).upper()
        if len(hexv) == 8:
            hexv = hexv[2:]          # strip AA
        out[name] = "#" + hexv
    if not out:
        die(f"parsed 0 color tokens from {path} - did the declaration style change?")
    return out


def parse_css(path):
    """Returns ({var: '#HEX'}, {var: 'raw value'}) for :root custom properties.

    Only the first declaration of each var wins, matching the cascade for the
    single :root block this stylesheet uses. Comments are stripped first so the
    historical hexes in the explanatory notes can't be mistaken for live values."""
    try:
        src = open(path, encoding="utf-8").read()
    except OSError as e:
        die(f"cannot read {path}: {e}")
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    colors, raw = {}, {}
    for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;]+);", src):
        var, val = m.group(1), m.group(2).strip()
        if var in raw:
            continue
        raw[var] = val
        hm = re.fullmatch(r"#([0-9A-Fa-f]{6})", val)
        if hm:
            colors[var] = "#" + hm.group(1).upper()
    return colors, raw


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app-repo", default=os.path.join(os.path.dirname(here), "meringo"),
                    help="path to the Meringo app repo (default: ../meringo)")
    ap.add_argument("--quiet", action="store_true", help="print only on failure")
    args = ap.parse_args()

    kt = os.path.join(args.app_repo, "core", "design", "src", "main", "kotlin",
                      "com", "meringo", "core", "design", "theme", "MeringoColors.kt")
    if not os.path.isfile(kt):
        die(f"app repo not found or moved - no MeringoColors.kt at:\n  {kt}\n"
            f"pass --app-repo. NOTE: this is 'unverified', not 'in sync'.")

    app = parse_kotlin_colors(kt)
    css, raw = parse_css(os.path.join(here, "colors_and_type.css"))

    drift, missing = [], []

    for var, token in sorted(COLOR_MAP.items()):
        if token not in app:
            missing.append(f"{token}: no longer declared in MeringoColors.kt (mapped from {var})")
            continue
        if var not in css:
            missing.append(f"{var}: not a plain hex :root var in colors_and_type.css")
            continue
        if css[var] != app[token]:
            drift.append((var, token, css[var], app[token]))

    for var, family in sorted(FONT_MAP.items()):
        val = raw.get(var)
        if val is None:
            missing.append(f"{var}: not declared in colors_and_type.css")
            continue
        first = val.split(",")[0].strip().strip("'\"")
        if first.lower() != family.lower():
            drift.append((var, "app res/font/", first, family))

    if not drift and not missing:
        if not args.quiet:
            print(f"check-brand-sync: OK - {len(COLOR_MAP)} color vars and "
                  f"{len(FONT_MAP)} font vars match the app.")
        return 0

    print("check-brand-sync: DRIFT - the website no longer matches the app.\n")
    if drift:
        w = max(len(d[0]) for d in drift)
        print(f"  {'css var'.ljust(w)}  {'app token':22}  {'site has':10}  app has")
        print(f"  {'-'*w}  {'-'*22}  {'-'*10}  {'-'*10}")
        for var, token, got, want in drift:
            print(f"  {var.ljust(w)}  {token:22}  {got:10}  {want}")
    if missing:
        print("\n  could not compare:")
        for m in missing:
            print(f"    - {m}")
    print("\n  The app is the source of truth - it ships, and its tokens are contrast-graded")
    print("  in docs/A11Y_CONTRAST_AUDIT.md. Normally you update the website to match.")
    print("  Remember the raw literals too: index.html carries ~119 hard-coded hex/rgba")
    print("  values, including inline SVG fill= attributes that cannot read CSS vars.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
