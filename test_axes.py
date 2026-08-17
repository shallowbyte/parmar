#!/usr/bin/env python3
"""Phase 5: verify every the design spec axis value round-trips, independently.

Each axis value gets its own compress+decompress with full sha256/length/token-count
verification against a real slice of the corpus, before it is allowed to consume
hours inside a full sweep. Small before big: this runs on a few MB, not on a tier.

Run: python test_axes.py [--corpus PATH] [--slice-mb N]
"""

import argparse
import os
import shutil
import sys
import tempfile

import parmar_core as core
import resources

FAILS = []


def check(label, fn):
    try:
        st, res = fn()
    except Exception as exc:
        print(f"  FAIL  {label:<62} {type(exc).__name__}: {exc}")
        FAILS.append(label)
        return
    if res["round_trip_verified"]:
        print(f"  PASS  {label:<62} {st['ratio']:>7.4f}x  "
              f"{st['compressed_bytes']:>11,}B")
    else:
        print(f"  FAIL  {label:<62} {'; '.join(res['errors'])}")
        FAILS.append(label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="./corpus/pg19_64mb.txt")
    ap.add_argument("--slice-mb", type=int, default=8)
    args = ap.parse_args()

    tools = resources.detect_tools()
    tmp = tempfile.mkdtemp(prefix="parmar_axes_")
    src = os.path.join(tmp, "slice.txt")
    n = args.slice_mb * 1024 * 1024
    with open(args.corpus, "rb") as fi:
        data = fi.read(n)
    data = data[:core.trim_to_utf8_boundary(data, len(data))]
    with open(src, "wb") as fo:
        fo.write(data)
    print(f"slice: {len(data):,} bytes from {args.corpus}\n")

    def run(tok, packing, backend, transport, layout, threads=4, chunk=None,
            batch=4):
        def go():
            arc = os.path.join(tmp, "a.parmar")
            st = core.compress_file(src, arc, tok, packing, backend, transport,
                                    layout, threads,
                                    chunk or core.CHUNK_SIZE, batch, tools=tools)
            res = core.decompress_file(arc, None, threads, tools=tools,
                                       decode_batch_tokens=50_000)
            os.unlink(arc)
            return st, res
        return go

    try:
        print("AXIS: backend x transport  (every backend, both transports)")
        for backend in core.BACKENDS:
            for transport in core.TRANSPORTS:
                pack = ("fixed_u16" if backend == "lzma_tuned_lp1pb1" else "leb128")
                tok = "r50k_base" if pack == "fixed_u16" else "o200k_base"
                check(f"{backend} / {transport} / {tok} / {pack}",
                      run(tok, pack, backend, transport, "library_batch"))

        print("\nAXIS: tokenizer x packing  (all valid pairs)")
        pairs = [("none", "raw_utf8"),
                 ("o200k_base", "leb128"), ("cl100k_base", "leb128"),
                 ("r50k_base", "leb128"), ("p50k_base", "leb128"),
                 ("r50k_base", "fixed_u16"), ("p50k_base", "fixed_u16")]
        for tok, pack in pairs:
            check(f"{tok} / {pack} / lzma_fast",
                  run(tok, pack, "lzma_fast", "subprocess_cli", "library_batch"))

        print("\nAXIS: tokenization_layout")
        for layout in core.TOKENIZATION_LAYOUTS:
            check(f"{layout} / o200k_base / leb128 / lzma_fast",
                  run("o200k_base", "leb128", "lzma_fast", "subprocess_cli", layout))

        print("\nAXIS: chunk_size")
        for cs in (1 << 20, 2 << 20, 4 << 20):
            check(f"chunk={cs >> 20}MB / o200k_base / leb128 / lzma_fast",
                  run("o200k_base", "leb128", "lzma_fast", "subprocess_cli",
                      "library_batch", chunk=cs))

        print("\nAXIS: threads")
        for th in (1, 4, 20):
            check(f"threads={th} / o200k_base / leb128 / lzma_fast",
                  run("o200k_base", "leb128", "lzma_fast", "subprocess_cli",
                      "library_batch", threads=th))

        print("\nAXIS: batch_chunks")
        for bc in (2, 4, 16):
            check(f"batch_chunks={bc} / o200k_base / leb128 / lzma_fast",
                  run("o200k_base", "leb128", "lzma_fast", "subprocess_cli",
                      "library_batch", batch=bc))

        print("\nINVALID COMBINATIONS must be refused, not silently coerced")
        for tok, pack, why in [
                ("o200k_base", "fixed_u16", "vocab 200019 > 65536"),
                ("none", "leb128", "no token ids"),
                ("o200k_base", "raw_utf8", "raw_utf8 needs tokenizer=none")]:
            try:
                run(tok, pack, "lzma_fast", "subprocess_cli", "library_batch")()
                print(f"  FAIL  {tok}/{pack} was ACCEPTED (should raise: {why})")
                FAILS.append(f"{tok}/{pack} not refused")
            except ValueError as exc:
                print(f"  PASS  {tok}/{pack} refused: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILURE(S):")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("every axis value round-trip verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
