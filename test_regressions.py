#!/usr/bin/env python3
"""Regression tests for the two defects found once parmar.py could actually be run.

Both were latent in the pre-execution version of parmar.py and both were reproduced
before being fixed (see parmar_core's module docstring). These tests exist so a
future refactor cannot quietly reintroduce them.

Run: python test_regressions.py
"""

import os
import sys
import tempfile

import parmar_core as core

FAILURES = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def test_utf8_boundary_unit():
    """trim_to_utf8_boundary must back off even when end == len(data)."""
    print("\n[1] UTF-8 boundary backoff at the end of the buffer")
    raw = ("x" * 10 + "é").encode("utf-8")          # 10 ASCII + 2-byte codepoint
    n = len(raw)
    check("complete sequence at tail is not trimmed",
          core.trim_to_utf8_boundary(raw, n) == n, f"-> {core.trim_to_utf8_boundary(raw, n)}")
    check("incomplete 2-byte sequence backs off",
          core.trim_to_utf8_boundary(raw, n - 1) == n - 2,
          f"-> {core.trim_to_utf8_boundary(raw, n - 1)} (want {n - 2})")

    for ch in ("é", "中", "\U0001F600"):
        b = ("a" + ch).encode("utf-8")
        width = len(b) - 1
        for cut in range(1, width):
            got = core.trim_to_utf8_boundary(b, 1 + cut)
            check(f"{ch!r} width={width} cut={cut} backs off to 1", got == 1, f"-> {got}")
        check(f"{ch!r} full width is kept",
              core.trim_to_utf8_boundary(b, 1 + width) == 1 + width)


def test_read_chunks_no_delimiter():
    """The original failure: a delimiter-free run past the lookahead window.

    Pre-fix this raised UnicodeDecodeError at byte 2,101,247.
    """
    print("\n[2] read_chunks over a delimiter-free run of multi-byte codepoints")
    ch, la = core.CHUNK_SIZE, core.MAX_LOOKAHEAD
    for filler in ("é", "中", "\U0001F600"):
        head = ("word " * (ch // 5))[:ch - 3]
        tail = filler * (la + 5000)
        payload = (head + tail).encode("utf-8")
        with tempfile.NamedTemporaryFile("wb", suffix=".txt", delete=False) as fh:
            fh.write(payload)
            path = fh.name
        try:
            rebuilt = b""
            ok, detail = True, ""
            with open(path, "rb") as f:
                try:
                    for chunk in core.read_chunks(f):
                        chunk.decode("utf-8", errors="strict")
                        rebuilt += chunk
                except UnicodeDecodeError as e:
                    ok, detail = False, f"UnicodeDecodeError: {e}"
            check(f"filler={filler!r} every chunk is valid UTF-8", ok, detail)
            check(f"filler={filler!r} chunks reassemble to the original",
                  rebuilt == payload,
                  f"{len(rebuilt)} vs {len(payload)} bytes")
        finally:
            os.unlink(path)


def test_decode_bytes_batch_boundary():
    """decode_bytes must be exact at any token split; decode() is not."""
    print("\n[3] token-batch boundary reassembly")
    import tiktoken
    for name in ("o200k_base", "cl100k_base"):
        enc = tiktoken.get_encoding(name)
        probes = ["\U0001F926\U0001F3FC‍♂️", "\U0001F600\U0001F600",
                  "中文测试", "क्षत्र",
                  "café naïve ça va"]
        worst = None
        allok = True
        for probe in probes:
            ids = enc.encode_ordinary(probe)
            orig = probe.encode("utf-8")
            for k in range(len(ids) + 1):
                fixed = enc.decode_bytes(ids[:k]) + enc.decode_bytes(ids[k:])
                if fixed != orig:
                    allok = False
                legacy = (enc.decode(ids[:k]).encode("utf-8")
                          + enc.decode(ids[k:]).encode("utf-8"))
                if legacy != orig and worst is None:
                    worst = (probe, k)
        check(f"{name}: decode_bytes exact at every split", allok)
        if worst:
            check(f"{name}: the old decode() path really was broken (probe split at "
                  f"token {worst[1]})", True)


def test_end_to_end_hostile_roundtrip():
    """Full compress/decompress over input built to hit both bugs at once."""
    print("\n[4] end-to-end round trip on hostile input")
    ch, la = core.CHUNK_SIZE, core.MAX_LOOKAHEAD
    parts = [("word " * (ch // 5))[:ch - 3],
             "\U0001F926\U0001F3FC‍♂️" * (la // 4 + 3000),
             " normal prose resumes here. " * 5000,
             "中文" * (la + 2000),
             " tail. "]
    payload = "".join(parts).encode("utf-8")

    tmp = tempfile.mkdtemp(prefix="parmar_regr_")
    src = os.path.join(tmp, "hostile.txt")
    with open(src, "wb") as f:
        f.write(payload)

    tools = __import__("resources").detect_tools()
    combos = [("o200k_base", "leb128", "lzma_fast", "subprocess_cli"),
              ("o200k_base", "leb128", "zstd_12", "in_process_binding"),
              ("r50k_base", "fixed_u16", "lzma_tuned_lp1pb1", "subprocess_cli"),
              ("none", "raw_utf8", "lzma_fast", "subprocess_cli")]
    try:
        for tok, packing, backend, transport in combos:
            arc = os.path.join(tmp, f"{tok}_{packing}_{backend}_{transport}.parmar")
            label = f"{tok}/{packing}/{backend}/{transport}"
            try:
                st = core.compress_file(src, arc, tok, packing, backend, transport,
                                        "library_batch", 4, core.CHUNK_SIZE, 8,
                                        tools=tools)
                # decode batch deliberately tiny so batch boundaries land mid-character
                res = core.decompress_file(arc, None, 4, tools=tools,
                                           decode_batch_tokens=997)
                check(f"{label} round-trips ({st['ratio']:.2f}x)",
                      res["round_trip_verified"], "; ".join(res["errors"]))
            except Exception as exc:
                check(f"{label} round-trips", False, f"{type(exc).__name__}: {exc}")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("parmar regression tests")
    test_utf8_boundary_unit()
    test_read_chunks_no_delimiter()
    test_decode_bytes_batch_boundary()
    test_end_to_end_hostile_roundtrip()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        return 1
    print("all regression tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
