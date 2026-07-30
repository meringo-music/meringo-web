#!/usr/bin/env python3
"""
check-disclosure-sync.py — fail if the website's network disclosures have drifted
from the app's actual networking code.

WHY THIS EXISTS
---------------
On 2026-07-30 the privacy policy on this site was telling users that their
acoustic fingerprints were "submitted to the AcoustID public API", and pointing
the opt-out at `Settings -> Library -> Identify unknown albums`. The app had
stopped making that call five days earlier and the Settings row was gone, so
anyone who followed the privacy policy in order to switch it off would not have
found the control.

Nobody lied. The app has NetworkClaimParityTest, which walks the networking code
and fails the build if any in-app disclosure surface omits a reachable server —
and it worked: the Field Guide, the Full Manual and the first-run consent screen
were all correct the whole time. It cannot see this repository. The same gap that
check-brand-sync.py closed for the palette was open for the disclosures.

This script is that binding, for the claims instead of the colors.

WHAT IT CHECKS
--------------
1. HOSTS. Every server the app can reach is named on this site, no server it
   cannot reach is named as a destination, and the two vendors with no hostname
   at all (Google Play, Sentry) are named while they are wired.

   The host list is NOT re-derived here. It is read from the app repo's
   docs/network-disclosure.json, which NetworkClaimParityTest generates from the
   same scan that guards the in-app surfaces and re-checks on every build. The
   scan is the subtle part — module derivation to a fixed point, bare-host
   literals, file-bound display-only exemptions — and a second implementation in
   another language would drift from it invisibly, because both would still emit
   a plausible list of hostnames. One scan, one answer, exported.

2. SETTINGS PATHS. Every `Settings -> ...` path this site tells a user to follow
   resolves to a string that still exists in the app's UI code. This is the half
   that caught the real bug.

USAGE
-----
    python tools/check-disclosure-sync.py                    # assumes ../meringo
    python tools/check-disclosure-sync.py --app-repo D:/src/meringo
    python tools/check-disclosure-sync.py --quiet            # only print on failure

Exit 0 = in sync. Exit 1 = drift. Exit 2 = couldn't run the check (app repo not
found, manifest missing or unparseable). Exit 2 is NOT a pass — it means
unverified, and a guard that passes silently when it cannot see the thing it
guards is worse than no guard.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It cannot check whether a claim is TRUE — only whether it names something that
still exists. Those are different failures, and both have happened here:

  - drift:     the site named a host and a Settings row the app had dropped.
               Mechanical. This script catches it.
  - invention: the same page described the album-confidence bar as agreement
               across "album title, artist, track count, runtime, fingerprint".
               There is no such blend; the value is MusicBrainz's own match
               score, capped at 0.80 for relaxed matches. That was never true —
               it did not drift — and no host list would ever have found it.

Prose that describes a mechanism still needs a human reading it against the
source. Do not let a green run here be mistaken for "the page is accurate".
"""

import argparse
import html
import json
import os
import re
import sys

# Every Settings path this script reports contains U+2192, and Windows consoles
# still default to cp1252 — so the failure branch died with UnicodeEncodeError
# while the passing branch was fine. A guard whose only untested path is the one
# that reports a problem is not a guard. (It even exited 1 on the crash, which is
# the drift code, so the breakage was wearing the right answer's clothes.)
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

INDEX = "index.html"
MANIFEST_REL = os.path.join("docs", "network-disclosure.json")

# Where the app's user-visible strings live. Settings-path segments are resolved
# against these trees only — a string that survives in, say, core/storage is not
# evidence that a Settings row still renders.
UI_SOURCE_DIRS = [("feature",), ("app", "src", "main")]

ARROW = r"\s*(?:&rarr;|\u2192)\s*"

# Paths are rendered inside a mono <span> or <code>; that element is the natural
# boundary. Matching raw prose instead runs the "path" on into the sentence after
# it and produces garbage segments that can never resolve.
ELEMENT_RE = re.compile(r"<(span|code)\b[^>]*>(.*?)</\1>", re.S | re.I)

# Segments that name a screen the app does not own, so there is nothing to
# resolve them against. Android's own Settings app is the only case today
# ("Android Settings -> Apps -> Meringo -> Storage -> Clear all data", in the
# GDPR erasure paragraph).
FOREIGN_PATH_ROOTS = ("Apps",)

# Hosts this site discloses by SERVICE NAME rather than by hostname, and the
# string that counts as naming each one.
#
# The app's surfaces print hostnames because a consent screen should be literal
# about what opens a socket. Prose for a general reader says "MusicBrainz", and
# demanding "musicbrainz.org" in the middle of a sentence would make the page
# worse, not more honest. So each host gets one explicit alias.
#
# This is a map with no default ON PURPOSE. A host the app gains is named
# nowhere and aliased nowhere, so it fails until somebody decides how this page
# should say it. That decision is the point; the alias is just where it is
# recorded. Do not add a wildcard.
HOST_ALIASES = {
    "musicbrainz.org": "MusicBrainz",
    "coverartarchive.org": "Cover Art Archive",
    "en.wikipedia.org": "Wikipedia",
    # Deliberately stricter than "Wikipedia": article text and the hero image it
    # carries come from two different hosts, and the ledger earns this one by
    # naming the operator — "Wikipedia (Wikimedia Foundation)".
    "upload.wikimedia.org": "Wikimedia",
}


def die(msg, code=2):
    print(f"check-disclosure-sync: {msg}", file=sys.stderr)
    sys.exit(code)


def load_manifest(app_repo):
    path = os.path.join(app_repo, MANIFEST_REL)
    if not os.path.isfile(path):
        die(f"app repo not found or manifest missing - no file at:\n  {path}\n"
            f"pass --app-repo, or regenerate it in the app repo with:\n"
            f"  ./gradlew :feature:settings:test -Dmeringo.writeDisclosureManifest=true\n"
            f"NOTE: this is 'unverified', not 'in sync'.")
    try:
        data = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        die(f"cannot parse {path}: {e}")
    reachable = data.get("reachableHosts") or []
    vendors = data.get("vendorDestinations") or []
    unreachable = data.get("unreachableHosts") or []
    # Fail closed. An empty reachable list would make every naming check pass
    # vacuously, which is exactly how a broken instrument reads as a clean bill.
    if not reachable:
        die(f"{path} lists no reachable hosts - the app scan is broken or the "
            f"manifest format changed. Refusing to report a pass.")
    return reachable, vendors, unreachable


def app_ui_code(app_repo):
    """The app's UI sources with comment lines dropped.

    Dropping comments is not tidiness, it is the whole correctness of check 2.
    When a row is deleted the removal usually leaves a tombstone behind
    ("Identify unknown albums (uses AcoustID) and its Deep Scan row lived
    here"), so a scan that reads comments cannot tell a live row from a deleted
    one — and would have passed on the bug this script was written for.
    """
    out = []
    for parts in UI_SOURCE_DIRS:
        base = os.path.join(app_repo, *parts)
        for root, _, files in os.walk(base):
            seg = root.split(os.sep)
            if "test" in seg or "androidTest" in seg:
                continue
            for f in files:
                if not f.endswith(".kt"):
                    continue
                try:
                    text = open(os.path.join(root, f), encoding="utf-8").read()
                except OSError:
                    continue
                for line in text.splitlines():
                    t = line.lstrip()
                    if t.startswith("*") or t.startswith("//") or t.startswith("/*"):
                        continue
                    out.append(line)
    if not out:
        die(f"read 0 lines of app UI source under {app_repo} - wrong --app-repo, or "
            f"the module layout moved. Refusing to report a pass.")
    return "\n".join(out).lower()


def settings_paths(doc):
    """Every `Settings -> ...` path the site tells a user to follow."""
    paths = []
    for m in ELEMENT_RE.finditer(doc):
        text = html.unescape(re.sub(r"<[^>]+>", "", m.group(2)))
        text = text.replace("\u00a0", " ").strip()
        if not re.match(r"^Settings" + ARROW, text):
            continue
        segs = [s.strip().rstrip(".,;") for s in re.split(ARROW, text)][1:]
        if segs and segs[0] in FOREIGN_PATH_ROOTS:
            continue
        paths.append((text, segs))
    return paths


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app-repo", default=os.path.join(os.path.dirname(here), "meringo"),
                    help="path to the Meringo app repo (default: ../meringo)")
    ap.add_argument("--quiet", action="store_true", help="print only on failure")
    args = ap.parse_args()

    reachable, vendors, unreachable = load_manifest(args.app_repo)

    index_path = os.path.join(here, INDEX)
    try:
        doc = open(index_path, encoding="utf-8").read()
    except OSError as e:
        die(f"cannot read {index_path}: {e}")

    undisclosed, overclaimed, dead_paths = [], [], []

    # A host counts as named anywhere on the page: the third-party ledger, the
    # permissions list and the consent narrative each name their own subset, and
    # requiring every host in every block would fail on true copy. Substring
    # matching mirrors the app-side test, where "api.listenbrainz.org" satisfies
    # a bare "listenbrainz.org" the same way.
    for host in reachable:
        if host in doc:
            continue
        alias = HOST_ALIASES.get(host)
        if alias and alias in doc:
            continue
        undisclosed.append(host if not alias else f"{host} (nor its alias {alias!r})")
    for vendor in vendors:
        if vendor not in doc:
            undisclosed.append(f"{vendor} (vendor-named: no hostname exists to print)")
    for host in unreachable:
        if host in doc:
            overclaimed.append(host)

    ui = app_ui_code(args.app_repo)
    paths = settings_paths(doc)
    for text, segs in paths:
        for seg in segs:
            if seg.lower() not in ui:
                dead_paths.append((text, seg))

    if not undisclosed and not overclaimed and not dead_paths:
        if not args.quiet:
            print(f"check-disclosure-sync: OK - {len(reachable)} hosts and {len(vendors)} "
                  f"vendor destinations named, {len(unreachable)} unreachable hosts absent, "
                  f"{len(paths)} Settings paths resolve.")
        return 0

    print("check-disclosure-sync: DRIFT - the website no longer matches the app.\n")

    if undisclosed:
        print("  Reachable but NOT named on the site:")
        for h in undisclosed:
            print(f"    - {h}")
        print("    The app can open a connection to these. Every disclosure surface")
        print("    is required to name them; this page makes the same promise.\n")

    if overclaimed:
        print("  Named on the site but NOT reachable by the app:")
        for h in overclaimed:
            print(f"    - {h}")
        print("    The client ships dormant with no caller. Telling users their data")
        print("    goes somewhere it cannot go is still a false disclosure.\n")

    if dead_paths:
        print("  Settings paths that no longer resolve:")
        for text, seg in dead_paths:
            print(f"    - {text!r}")
            print(f"        segment {seg!r} is not in the app's UI code")
        print("    A user following this path will not find the control.\n")

    print("  The app is the source of truth - it ships. Normally you update this site.")
    print("  The host list comes from the app's docs/network-disclosure.json, which")
    print("  NetworkClaimParityTest regenerates and re-checks on every build.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
