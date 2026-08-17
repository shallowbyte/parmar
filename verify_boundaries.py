#!/usr/bin/env python3
"""Boundary-safety differential test. BLOCKING.

The whole harness rests on one unverified assumption: that splitting the input at
parmar's chunk boundaries produces the *same token sequence* as tokenizing the stream
unsplit. If that is false, chunk size silently perturbs the token stream, every ratio
in the matrix picks up tokenizer-specific noise that looks like real signal, and the
scale curve the project exists to measure becomes uninterpretable.

The assumption is plausible because tiktoken's BPE is pretoken-scoped -- the regex
splits the text into pretokens first and merges never cross a pretoken boundary -- so
a cut that lands on a pretoken boundary is invisible to the tokenizer. parmar cuts at
whitespace/punctuation, which *should* always be a pretoken boundary. "Should" is not
a measurement, and the design spec explicitly notes this was never checked against any
tokenizer, and never at all against cl100k_base/r50k_base/p50k_base whose
pretokenization patterns differ from o200k_base's.

This is deliberately a standalone script rather than a step folded into the sweep: a
failure here has to block the sweep, not surface later as an odd ratio outlier.

Run:
  python verify_boundaries.py --corpus ./corpus/pg19_64mb.txt \
      --tokenizers o200k_base,cl100k_base,r50k_base,p50k_base \
      --chunk-sizes 1MB,2MB,4MB
"""

import argparse
import io
import os
import sys
import time

import parmar_core as core

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

SIZE_SUFFIX = {"KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}


def parse_size(s):
    s = s.strip().upper()
    for suf, mult in SIZE_SUFFIX.items():
        if s.endswith(suf):
            return int(float(s[:-len(suf)]) * mult)
    return int(s)


def tokenize_whole(enc, data):
    return enc.encode_ordinary(data.decode("utf-8"))


def tokenize_split(enc, data, chunk_size, lookahead=None, stats=None):
    """Tokenize via parmar's actual chunker, then concatenate the id sequences."""
    ids = []
    boundaries = []
    offset = 0
    la = lookahead if lookahead is not None else core.MAX_LOOKAHEAD
    with io.BytesIO(data) as fh:
        for chunk in core.read_chunks(fh, chunk_size, la, stats=stats):
            offset += len(chunk)
            boundaries.append(offset)
            ids.extend(enc.encode_ordinary(chunk.decode("utf-8")))
    return ids, boundaries


def first_divergence(a, b):
    n = min(len(a), len(b))
    if HAS_NUMPY and n:
        aa = np.asarray(a[:n], dtype=np.int64)
        bb = np.asarray(b[:n], dtype=np.int64)
        diff = np.nonzero(aa != bb)[0]
        if diff.size:
            return int(diff[0])
    else:
        for i in range(n):
            if a[i] != b[i]:
                return i
    return None if len(a) == len(b) else n


def report_divergence(enc, whole, split, boundaries, data):
    idx = first_divergence(whole, split)
    print(f"      first divergence at token index {idx}")
    lo = max(0, idx - 6)
    hi = idx + 6
    print(f"      unsplit tokens[{lo}:{hi}] = {list(whole[lo:hi])}")
    print(f"      split   tokens[{lo}:{hi}] = {list(split[lo:hi])}")
    try:
        prefix = enc.decode_bytes(list(whole[:idx]))
        byte_off = len(prefix)
        print(f"      approx byte offset {byte_off:,}")
        near = [b for b in boundaries if abs(b - byte_off) < 4096]
        print(f"      chunk boundaries within 4KB: {near}")
        ctx = data[max(0, byte_off - 60):byte_off + 60]
        print(f"      context: {ctx.decode('utf-8', errors='replace')!r}")
    except Exception as exc:
        print(f"      (could not localize: {exc})")


def run_corpus_case(enc, name, data, chunk_size, label, whole=None):
    t0 = time.perf_counter()
    if whole is None:
        whole = tokenize_whole(enc, data)
    t1 = time.perf_counter()
    stats = {"unsafe_boundary_cuts": 0}
    split, boundaries = tokenize_split(enc, data, chunk_size, stats=stats)
    t2 = time.perf_counter()

    same = len(whole) == len(split) and (
        bool(np.array_equal(np.asarray(whole, dtype=np.int64),
                            np.asarray(split, dtype=np.int64))) if HAS_NUMPY
        else whole == split)

    status = "IDENTICAL" if same else "*** DIVERGED ***"
    unsafe = stats["unsafe_boundary_cuts"]
    print(f"    {label:<10} {len(whole):>12,} tokens / {len(boundaries):>4} chunks   "
          f"{status}   (split {t2-t1:.1f}s, unsafe cuts: {unsafe})")
    if unsafe:
        print(f"      ! {unsafe} chunk(s) had no tokenizer-safe cut point within the "
              f"{core.MAX_LOOKAHEAD:,}-byte lookahead")
    if not same:
        print(f"      unsplit produced {len(whole):,} tokens, split produced "
              f"{len(split):,}")
        report_divergence(enc, whole, split, boundaries, data)
    return same


ADVERSARIAL = [
    # Constructs the design spec flags as risky, each repeated long enough that many
    # chunk boundaries land inside it.
    ("long digit run", "1234567890" * 4000),
    ("digits with separators", "12,345,678.90 " * 3000),
    ("leading-space word run", " supercalifragilistic" * 2500),
    ("digits split by spaces", "1 22 333 4444 55555 " * 2500),
    ("no-whitespace letter run", "z" * 300000),
    ("punctuation storm", ".,;:!?\"')]}" * 4000),
    ("multi-byte run", "é中\U0001F600" * 4000),
    ("mixed digits and letters", "abc123def456 " * 3000),
    ("newline heavy", "line\r\n" * 8000),
    ("crlf paragraph breaks", "Some prose here.\r\n\r\nMore prose.\r\n" * 2000),
    ("contractions and quotes", "don't “quote” it's " * 3000),
    ("tabs and mixed space", "word\t \t word  \r\n   word " * 2500),
    ("caps and mixed case", "WORD Word wORD WoRd " * 3000),
]

# The adversarial block deliberately uses a small chunk size rather than the real
# 1/2/4MB values. The cut rule is chunk-size-agnostic, so shrinking the chunk gives
# far more boundaries per byte -- thousands of distinct cut points through each
# construct instead of one -- at a tiny fraction of the tokenization cost. Real
# chunk sizes are covered by the corpus block above, on real text.
ADV_CHUNK = 4096
ADV_LOOKAHEAD = 2048


def run_adversarial(enc, name):
    """Returns (hard_fail, n_expected_limitations).

    A divergence only counts as a failure of the cut rule if the chunker actually
    found safe cut points and the tokens still disagreed. A divergence on input that
    contains no safe cut point at all (an unbroken digit run, a pure-punctuation
    blob) is a known and reported limitation of the rule, not a bug in it -- so the
    two are separated instead of both being called "FAIL".
    """
    hard_fail = False
    limitations = []
    clean = 0
    total_boundaries = 0
    for case_name, text in ADVERSARIAL:
        data = text.encode("utf-8")
        whole = tokenize_whole(enc, data)
        stats = {"unsafe_boundary_cuts": 0}
        split, boundaries = tokenize_split(enc, data, ADV_CHUNK, ADV_LOOKAHEAD, stats)
        total_boundaries += max(len(boundaries) - 1, 0)
        unsafe = stats["unsafe_boundary_cuts"]
        if whole == split:
            clean += 1
            if unsafe:
                limitations.append(f"{case_name} ({unsafe} unsafe cuts, but tokens "
                                   f"happened to match)")
            continue
        idx = first_divergence(whole, split)
        if unsafe:
            limitations.append(f"{case_name} ({unsafe} unsafe cuts -> "
                               f"{len(whole)} vs {len(split)} tokens)")
            continue
        hard_fail = True
        print(f"    adversarial '{case_name}' *** DIVERGED WITH ZERO UNSAFE CUTS *** "
              f"({len(whole)} vs {len(split)} tokens, first at index {idx})")
        lo, hi = max(0, idx - 4), idx + 4
        print(f"      unsplit {list(whole[lo:hi])}")
        print(f"      split   {list(split[lo:hi])}")

    print(f"    adversarial: {clean}/{len(ADVERSARIAL)} constructs token-identical "
          f"across {total_boundaries:,} boundaries at {ADV_CHUNK}B chunks")
    for lim in limitations:
        print(f"      (known limitation) {lim}")
    return not hard_fail, len(limitations)


def main():
    ap = argparse.ArgumentParser(
        description="Boundary-safety differential test")
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--tokenizers",
                    default="o200k_base,cl100k_base,r50k_base,p50k_base")
    ap.add_argument("--chunk-sizes", default="1MB,2MB,4MB")
    ap.add_argument("--sample-bytes", type=str, default="64MB",
                    help="how much of the corpus to test (from the start)")
    ap.add_argument("--skip-adversarial", action="store_true")
    args = ap.parse_args()

    tokenizers = [t.strip() for t in args.tokenizers.split(",") if t.strip()]
    chunk_sizes = [(c.strip(), parse_size(c)) for c in args.chunk_sizes.split(",")
                   if c.strip()]
    sample = parse_size(args.sample_bytes)

    if not os.path.exists(args.corpus):
        print(f"corpus not found: {args.corpus}", file=sys.stderr)
        return 2

    size = os.path.getsize(args.corpus)
    with open(args.corpus, "rb") as fh:
        data = fh.read(min(sample, size))
    # Do not cut the sample mid-codepoint; that would be this test's bug, not parmar's.
    data = data[:core.trim_to_utf8_boundary(data, len(data))]

    print("=" * 78)
    print("Boundary-safety differential test")
    print("=" * 78)
    print(f"corpus      {args.corpus} ({size:,} bytes)")
    print(f"sample      {len(data):,} bytes")
    print(f"tokenizers  {', '.join(tokenizers)}")
    print(f"chunk sizes {', '.join(c for c, _ in chunk_sizes)}")
    print("property    tokenize(whole) == concat(tokenize(chunk) for each chunk)")
    print()

    import tiktoken
    all_ok = True
    results = []
    for name in tokenizers:
        try:
            enc = tiktoken.get_encoding(name)
        except Exception as exc:
            print(f"  {name}: could not load ({exc}); SKIPPED with reason logged")
            all_ok = False
            continue
        print(f"  {name} (vocab={enc.n_vocab:,})")
        t0 = time.perf_counter()
        whole = tokenize_whole(enc, data)
        print(f"    unsplit reference: {len(whole):,} tokens in "
              f"{time.perf_counter() - t0:.1f}s")
        for label, cs in chunk_sizes:
            ok = run_corpus_case(enc, name, data, cs, label, whole=whole)
            results.append((name, label, "corpus", ok))
            all_ok = all_ok and ok
        if not args.skip_adversarial:
            aok, nlim = run_adversarial(enc, name)
            results.append((name, "-", "adversarial", aok))
            all_ok = all_ok and aok
        print()

    print("=" * 78)
    npass = sum(1 for *_, ok in results if ok)
    print(f"{npass}/{len(results)} checks identical")
    if all_ok:
        print("RESULT: PASS -- chunk-boundary splitting is token-identical for every "
              "tokenizer x chunk-size combination run.")
        print("The sweep may proceed.")
        return 0
    print("RESULT: FAIL -- chunking perturbs the token stream. The sweep MUST NOT "
          "run until this is fixed; every downstream ratio would carry "
          "tokenizer-specific noise indistinguishable from real signal.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
