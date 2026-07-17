#!/usr/bin/env python3
# meringo-verify.py — recompute a Meringo bit-perfect receipt's hash with
# software that shares no code with Meringo.
#
# A Meringo receipt claims: the bytes shipped down the USB isochronous pipe
# to the DAC (capture SHA-256) equal the file's own decoded PCM laid out in
# the same byte order (source SHA-256). This script recomputes that layout
# hash from YOUR copy of the file using YOUR locally installed ffmpeg, so
# the receipt's reference can be checked against a decoder and a hash
# implementation Meringo doesn't control.
#
# Full method: https://meringo.app/verify/
#
# Usage:
#   python meringo-verify.py track.flac --bit-depth 16 --expect <sha256>
#   python meringo-verify.py track.flac --bit-depth 24 --bytes 1481754
#
#   --bit-depth  the bit depth on the receipt's Format line — the width of
#                the USB slot the DAC opened (16, 24, or 32)
#   --expect     either SHA-256 from the receipt; on a BIT-IDENTICAL receipt
#                both hashes are the same value
#   --bytes      the receipt's "Source bytes hashed" — only needed when the
#                capture didn't cover the whole track (partial receipts)
#
# Requires: Python 3.8+ and ffmpeg (ffprobe ships with it) on PATH, or
# passed via --ffmpeg / --ffprobe.
#
# This file is public domain (CC0 1.0). No warranty. It's short on purpose —
# read it before you run it.

import argparse
import hashlib
import shutil
import subprocess
import sys

FMT_BY_DEPTH = {16: "s16le", 24: "s24le", 32: "s32le"}
CHUNK = 1 << 16


def fail(msg):
    print("error: " + msg, file=sys.stderr)
    sys.exit(2)


def probe_native_bits(ffprobe, path):
    """The file's native bit depth via ffprobe, or None if undeterminable."""
    if not ffprobe:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=bits_per_raw_sample,bits_per_sample",
             "-of", "default=noprint_wrappers=1", path],
            capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    values = {}
    for line in out.strip().splitlines():
        if "=" in line:
            key, _, val = line.partition("=")
            values[key] = val
    for key in ("bits_per_raw_sample", "bits_per_sample"):
        val = values.get(key, "")
        if val.isdigit() and int(val) > 0:
            return int(val)
    return None


def main():
    ap = argparse.ArgumentParser(
        description="Independently recompute a Meringo bit-perfect receipt's hash.",
    )
    ap.add_argument("file", help="your copy of the audio file on the receipt")
    ap.add_argument("--bit-depth", type=int, required=True, choices=sorted(FMT_BY_DEPTH),
                    help="bit depth from the receipt's Format line (the USB slot width)")
    ap.add_argument("--expect", metavar="SHA256",
                    help="a SHA-256 from the receipt to compare against")
    ap.add_argument("--bytes", type=int, metavar="N", dest="byte_limit",
                    help="hash only the first N bytes (the receipt's 'Source bytes hashed')")
    ap.add_argument("--ffmpeg", default=None, help="path to ffmpeg (default: found on PATH)")
    ap.add_argument("--ffprobe", default=None, help="path to ffprobe (default: found on PATH)")
    args = ap.parse_args()

    ffmpeg = args.ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        fail("ffmpeg not found -- install it (ffmpeg.org) or pass --ffmpeg")
    ffprobe = args.ffprobe or shutil.which("ffprobe")

    # The receipt's Format line names the width of the slot the DAC opened.
    # Decoding straight to that width reproduces Meringo's layout exactly:
    #  - equal widths: the decode is untouched, sample for sample;
    #  - 16-bit file into a 24-bit slot: each sample gains a zero low byte
    #    (0x00, LSB, MSB — the value shifted left 8 bits), which is both
    #    what Meringo ships to the DAC and what ffmpeg's own s16-to-s24
    #    conversion produces. Same bytes, independent implementations.
    # A file DEEPER than the slot is not a layout Meringo will ever hash —
    # its own receipt reads inconclusive/mismatch there — and ffmpeg would
    # silently truncate samples, so refuse rather than mislead.
    native_bits = probe_native_bits(ffprobe, args.file)
    layout_note = "%d-bit little-endian, channels interleaved" % args.bit_depth
    if native_bits is not None:
        if native_bits > args.bit_depth:
            fail("this file is %d-bit but the receipt says a %d-bit slot; narrowing is "
                 "not a bit-perfect layout and Meringo's own receipt reports it as such"
                 % (native_bits, args.bit_depth))
        if native_bits < args.bit_depth:
            layout_note += (" (%d-bit source, zero-padded low byte%s)"
                            % (native_bits,
                               "" if (native_bits, args.bit_depth) == (16, 24)
                               else " -- NOT a layout Meringo documents"))
    else:
        print("note: couldn't probe the file's native bit depth; proceeding", file=sys.stderr)

    proc = subprocess.Popen(
        [ffmpeg, "-v", "error", "-nostdin", "-i", args.file,
         "-map", "0:a:0", "-f", FMT_BY_DEPTH[args.bit_depth], "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    digest = hashlib.sha256()
    hashed = 0
    decoded = 0
    limit = args.byte_limit
    while True:
        chunk = proc.stdout.read(CHUNK)
        if not chunk:
            break
        decoded += len(chunk)
        if limit is None:
            take = len(chunk)
        else:
            take = max(0, min(len(chunk), limit - hashed))
        if take:
            digest.update(chunk[:take])
            hashed += take
    stderr = proc.stderr.read().decode(errors="replace").strip()
    if proc.wait() != 0:
        fail("ffmpeg failed to decode %s%s" % (args.file, "\n" + stderr if stderr else ""))

    computed = digest.hexdigest()
    print("  file         : %s" % args.file)
    print("  layout       : %s" % layout_note)
    print("  bytes hashed : {:,} (of {:,} decoded)".format(hashed, decoded))
    print("  SHA-256      : %s" % computed)

    if limit is not None and hashed < limit:
        print("  WARNING      : the receipt hashed {:,} bytes but this file only decodes "
              "to {:,} — this is not the same audio the receipt covered".format(limit, decoded))

    if args.expect:
        expected = args.expect.strip().lower()
        print("  receipt says : %s" % expected)
        if computed == expected:
            print("  VERDICT      : MATCH -- the receipt's hash is reproducible "
                  "outside Meringo, from your copy of the file")
            return 0
        print("  VERDICT      : NO MATCH -- this file's PCM, laid out as the receipt "
              "describes, does not hash to the receipt's value")
        return 1
    print("  (no --expect given; compare the SHA-256 above to the receipt yourself)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
