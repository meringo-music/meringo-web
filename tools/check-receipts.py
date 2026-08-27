#!/usr/bin/env python3
"""
check-receipts.py — fail if the receipt registry's HTML has drifted out of
internal consistency, or the homepage's summary of it no longer matches.

WHY THIS EXISTS
---------------
The receipt registry (receipts/index.html) is a hand-curated microformat. Each
entry is an <article class="rcard"> carrying a DAC name, a verdict, a wire
format, an exact build, a date, and a full SHA-256. The maintainer picks which
captures to publish, redacts file names, and writes the per-DAC descriptor line
by hand — so there is no generated artifact to diff against, and never will be.
That curation is the point (see desk/DECISIONS.md, "refreshed by hand").

But a hand-authored ledger has hand-authored failure modes, and they are all
mechanical:

  - the homepage says "six receipts" and the registry now holds seven, because
    a card was added and the count sentence was not bumped;
  - a truncated hash on the homepage proof card (cb459147...295adf) points at a
    receipt that was removed or renumbered;
  - a shared-hash pair loses one of its "pair" markers, so the "two DACs, one
    hash" claim and the cards that back it fall out of agreement;
  - a hash is pasted 63 chars long, or in uppercase, or a build line is mangled.

None of these is a lie and none is a matter of taste. They are drift between
records that are supposed to agree, and a machine should catch them before a
push (this repo deploys on push; there is no CI). That is what this script is.

WHAT IT CHECKS
--------------
1. CARD SHAPE. Every rcard has a DAC, a verdict, a meta block and a hash. Each
   hash is exactly 64 lowercase hex. Each meta names a parseable
   `Meringo X.Y.Z (NNN)` build, a real ISO date, a kHz rate and a bit depth.
   Each verdict is one this registry actually uses.

2. PAIRS. If one hash appears on two or more cards ("same file, same hash,
   different DAC"), every one of those cards must carry the `pair` class and a
   `pair-note`, and the `.pair-callout` block must call that hash out. And the
   converse: a card marked `pair` whose hash is unique is a broken pair.

3. TRUNCATIONS. Every `prefix...suffix` hash shown outside the registry — the
   pair callout, the homepage proof card — resolves to exactly one full
   registry hash. A truncation that matches nothing means the surface points at
   a receipt that is not published.

4. THE HOMEPAGE COUNT. The "N DACs and M receipts" sentence on the homepage
   equals the registry's real distinct-DAC and card counts. This is the check
   that catches the forgotten bump when a card is added.

USAGE
-----
    python tools/check-receipts.py                 # both files, this repo
    python tools/check-receipts.py --receipts X --index Y   # point elsewhere
    python tools/check-receipts.py --quiet         # print only on failure

Exit 0 = consistent. Exit 1 = drift. Exit 2 = couldn't run the check (a file is
missing or unreadable, no cards parsed, or the count sentence could not be
located). Exit 2 is NOT a pass — it means unverified, and a guard that passes
silently when it cannot see the thing it guards is worse than no guard.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It grades SHAPE and INTERNAL CONSISTENCY, not truth. It cannot and does not:

  - check whether a hash is the real SHA-256 of anything. That is the reader's
    job, done with tools this project does not control, at /verify/. A card can
    be perfectly well-formed and carry an invented hash; only recomputation
    catches that, and a green run here must never be read as "the hash is real".
  - check the per-DAC USB descriptor line ("UAC2 high-speed async ..."). It is
    human-authored, is not in the receipt export, and has no in-repo reference.
  - check that a capture ever happened, or that the build named on a card was
    the build that produced it.
  - machine-verify the homepage's per-DAC rate ENUMERATION prose ("Fosi DS2 at
    both 16/44.1 and 24/96 ..."). Only the two head-counts are checked; the
    breakdown still needs a human reading it against the registry.

It reads two files in ONE repo. It does not read the app repo and does not fetch
any URL — on purpose. Coupling this to a live page would let a deploy-on-push
hash become assertable before a human had looked at it, which is the exact
checkpoint the registry's hand-curation exists to keep.
"""

import argparse
import html
import os
import re
import sys

# The failure branch prints hashes and a U+2026 or two, and Windows consoles
# still default to cp1252 — so without this the reporting path would die with
# UnicodeEncodeError while the passing path stayed fine. A guard whose only
# untested path is the one that reports a problem is not a guard.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

RECEIPTS_REL = os.path.join("receipts", "index.html")
INDEX_REL = "index.html"

# Verdicts this registry actually uses or documents. An unrecognised verdict is
# treated as drift, not waved through: a new verdict class is exactly the kind
# of thing a human should eyeball before it ships. Normalised form is what
# html.unescape + whitespace-collapse produces (so &#10003; is a literal check).
ALLOWED_VERDICTS = {
    "BIT-IDENTICAL ✓",
    "NOT BIT-IDENTICAL",
    "INCONCLUSIVE",
}

NUM_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}

ARTICLE_RE = re.compile(r'<article class="(rcard[^"]*)">(.*?)</article>', re.S | re.I)
DAC_RE = re.compile(r'<span class="rcard-dac">(.*?)</span>', re.S)
VERDICT_RE = re.compile(r'<span class="rcard-verdict">(.*?)</span>', re.S)
META_RE = re.compile(r'<p class="rcard-meta">(.*?)</p>', re.S)
# rcard-hash holds one <span class="hash-label">...</span> then the bare hex.
HASH_RE = re.compile(r'<p class="rcard-hash">.*?</span>([^<]+)</p>', re.S)
NOTE_CLASS_RE = re.compile(r'<p class="(rcard-note[^"]*)">', re.S)
CALLOUT_RE = re.compile(r'<div class="pair-callout">(.*?)</div>', re.S)

BUILD_RE = re.compile(r"Meringo\s+(\d+\.\d+\.\d+)\s*\((\d+)\)")
DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
RATE_RE = re.compile(r"\d+(?:\.\d+)?\s*kHz")
DEPTH_RE = re.compile(r"\d+-bit")
# A shortened hash: hex, an ellipsis (&hellip; / U+2026 / three dots), more hex.
TRUNC_RE = re.compile(r"([0-9a-f]{6,})(?:&hellip;|…|\.\.\.)([0-9a-f]{4,})")
# "... across three DACs and six receipts ..." — the one summary head-count.
COUNT_RE = re.compile(r"across\s+([A-Za-z0-9]+)\s+DACs?\s+and\s+([A-Za-z0-9]+)\s+receipts?", re.I)

HEX64 = re.compile(r"[0-9a-f]{64}")


def die(msg, code=2):
    print(f"check-receipts: {msg}", file=sys.stderr)
    sys.exit(code)


def read(path, label):
    if not os.path.isfile(path):
        die(f"{label} not found - no file at:\n  {path}\n"
            f"pass --{label}, or run this from the meringo-web repo. "
            f"NOTE: this is 'unverified', not 'consistent'.")
    try:
        return open(path, encoding="utf-8").read()
    except OSError as e:
        die(f"cannot read {path}: {e}")


def text_of(fragment):
    """Tag-stripped, entity-decoded, whitespace-collapsed text of an HTML bit."""
    t = re.sub(r"<[^>]+>", " ", fragment)
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def word_to_int(w):
    w = w.strip().lower()
    if w.isdigit():
        return int(w)
    return NUM_WORDS.get(w)


class Card:
    __slots__ = ("classes", "dac", "verdict", "meta", "hash", "note_classes", "problems")

    def __init__(self, class_attr, inner):
        self.classes = class_attr.split()
        self.problems = []

        dac = DAC_RE.search(inner)
        verdict = VERDICT_RE.search(inner)
        meta = META_RE.search(inner)
        hsh = HASH_RE.search(inner)
        self.note_classes = NOTE_CLASS_RE.findall(inner)

        self.dac = text_of(dac.group(1)) if dac else None
        self.verdict = text_of(verdict.group(1)) if verdict else None
        self.meta = text_of(meta.group(1)) if meta else None
        self.hash = hsh.group(1).strip() if hsh else None

    @property
    def is_pair(self):
        return "pair" in self.classes

    @property
    def has_pair_note(self):
        return any("pair-note" in c for c in self.note_classes)

    def label(self):
        return self.dac or "(card with no DAC name)"


def parse_cards(doc):
    cards = []
    for m in ARTICLE_RE.finditer(doc):
        cards.append(Card(m.group(1), m.group(2)))
    return cards


def resolve(pre, suf, all_hashes):
    return [h for h in all_hashes if h.startswith(pre) and h.endswith(suf)]


def main():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--receipts", default=os.path.join(repo, RECEIPTS_REL),
                    help="path to receipts/index.html")
    ap.add_argument("--index", default=os.path.join(repo, INDEX_REL),
                    help="path to the homepage index.html")
    ap.add_argument("--quiet", action="store_true", help="print only on failure")
    args = ap.parse_args()

    receipts_doc = read(args.receipts, "receipts")
    index_doc = read(args.index, "index")

    cards = parse_cards(receipts_doc)
    if not cards:
        die("parsed 0 rcard entries from the registry - the microformat changed "
            "or the file is wrong. Refusing to report consistency.")

    problems = []  # (card-or-None, message)

    # --- 1. Card shape -----------------------------------------------------
    all_hashes = []
    for c in cards:
        if c.dac is None:
            problems.append((c, "no <span class=\"rcard-dac\"> - malformed card"))
        if c.verdict is None:
            problems.append((c, "no <span class=\"rcard-verdict\">"))
        elif c.verdict not in ALLOWED_VERDICTS:
            problems.append((c, f"unrecognised verdict {c.verdict!r} - if this is a "
                                f"new legitimate verdict, add it to ALLOWED_VERDICTS"))
        if c.meta is None:
            problems.append((c, "no <p class=\"rcard-meta\">"))
        else:
            if not BUILD_RE.search(c.meta):
                problems.append((c, "meta has no parseable 'Meringo X.Y.Z (NNN)' build"))
            dm = DATE_RE.search(c.meta)
            if not dm:
                problems.append((c, "meta has no ISO YYYY-MM-DD date"))
            else:
                y, mo, d = map(int, dm.groups())
                if not (1 <= mo <= 12 and 1 <= d <= 31):
                    problems.append((c, f"meta date {dm.group(0)} is not a real calendar date"))
            if not RATE_RE.search(c.meta):
                problems.append((c, "meta names no kHz sample rate"))
            if not DEPTH_RE.search(c.meta):
                problems.append((c, "meta names no N-bit depth"))

        if c.hash is None:
            problems.append((c, "no hash in <p class=\"rcard-hash\">"))
        elif not re.fullmatch(r"[0-9a-f]{64}", c.hash):
            why = ("wrong length: %d chars, want 64" % len(c.hash)
                   if len(c.hash) != 64 else "not all lowercase hex")
            problems.append((c, f"malformed SHA-256 ({why}): {c.hash!r}"))
        else:
            all_hashes.append(c.hash)

    # --- 2. Pairs ----------------------------------------------------------
    by_hash = {}
    for c in cards:
        if c.hash:
            by_hash.setdefault(c.hash, []).append(c)

    callout_m = CALLOUT_RE.search(receipts_doc)
    callout_truncs = TRUNC_RE.findall(callout_m.group(1)) if callout_m else []

    shared = {h: cs for h, cs in by_hash.items() if len(cs) >= 2}
    for h, cs in shared.items():
        for c in cs:
            if not c.is_pair:
                problems.append((c, f"shares hash {h[:8]}... with another card but is "
                                    f"not marked class=\"rcard pair\""))
            if not c.has_pair_note:
                problems.append((c, f"shares hash {h[:8]}... but carries no pair-note"))
        if not callout_m:
            problems.append((None, f"hash {h[:8]}... is shared across "
                                   f"{len(cs)} cards but there is no .pair-callout block"))
        elif not any(resolve(p, s, [h]) for p, s in callout_truncs):
            problems.append((None, f"shared hash {h[:8]}...{h[-7:]} is not called out in "
                                   f"the .pair-callout block"))

    for c in cards:
        if c.is_pair and c.hash and len(by_hash.get(c.hash, [])) < 2:
            problems.append((c, "marked class=\"rcard pair\" but its hash is unique - "
                                "a pair lost its partner"))

    # --- 3. Truncations resolve (both pages) -------------------------------
    # Against DISTINCT hash values: a shared-hash pair is two cards but one
    # hash, and a truncation of it resolves to that one value, not "ambiguous".
    distinct_hashes = list(dict.fromkeys(all_hashes))
    for label, doc in (("registry", receipts_doc), ("homepage", index_doc)):
        for pre, suf in TRUNC_RE.findall(doc):
            hits = resolve(pre, suf, distinct_hashes)
            if len(hits) == 0:
                problems.append((None, f"truncated hash {pre}...{suf} on the {label} "
                                       f"matches no published registry entry"))
            elif len(hits) > 1:
                problems.append((None, f"truncated hash {pre}...{suf} on the {label} is "
                                       f"ambiguous - it matches {len(hits)} entries"))

    # --- 4. Homepage head-count -------------------------------------------
    matches = COUNT_RE.findall(index_doc)
    if len(matches) == 0:
        die("could not find the 'N DACs and M receipts' summary sentence on the "
            "homepage. If the wording changed, update COUNT_RE. Refusing to report "
            "a pass while the claim it guards is out of view.")
    if len(matches) > 1:
        problems.append((None, f"the 'N DACs and M receipts' sentence appears "
                               f"{len(matches)} times on the homepage - expected one"))
    dac_word, receipt_word = matches[0]
    claimed_dacs = word_to_int(dac_word)
    claimed_receipts = word_to_int(receipt_word)
    real_dacs = len({c.dac for c in cards if c.dac})
    real_receipts = len(cards)
    if claimed_dacs is None:
        problems.append((None, f"homepage DAC count {dac_word!r} is not a number I know"))
    elif claimed_dacs != real_dacs:
        problems.append((None, f"homepage says {dac_word} DACs; registry has {real_dacs} distinct"))
    if claimed_receipts is None:
        problems.append((None, f"homepage receipt count {receipt_word!r} is not a number I know"))
    elif claimed_receipts != real_receipts:
        problems.append((None, f"homepage says {receipt_word} receipts; registry has {real_receipts} cards"))

    # --- Report ------------------------------------------------------------
    if not problems:
        if not args.quiet:
            npair = sum(len(cs) for cs in shared.values())
            print(f"check-receipts: OK - {real_receipts} receipts across {real_dacs} DACs, "
                  f"{len(all_hashes)} valid hashes ({npair} in {len(shared)} shared pair(s)), "
                  f"all truncations resolve, homepage count matches.")
        return 0

    print("check-receipts: DRIFT - the registry and the pages that summarise it disagree.\n")
    for c, msg in problems:
        if c is None:
            print(f"    - {msg}")
        else:
            print(f"    - [{c.label()}] {msg}")
    print("\n  The registry is the ledger of record. Fix the card, or the homepage")
    print("  summary that describes it, so the two agree. This checks shape and")
    print("  internal consistency only - never whether a hash is real (that is /verify/).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
