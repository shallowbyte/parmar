#!/usr/bin/env python3
"""parmar: streaming subword-domain compression.

This is the original single-pipeline CLI, now delegating to `parmar_core` so the
baseline cell of the matrix and every other cell run the exact same code path.
The defaults here reproduce the original prototype: o200k_base + LEB128 + LZMA2
piped through the `xz` CLI.

Two defects present in the pre-execution version of this file are fixed in
`parmar_core` and documented there: the no-op UTF-8 chunk-boundary backoff, and
the use of `enc.decode()` (errors="replace") instead of `enc.decode_bytes()` when
reassembling token batches during decompression.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

import parmar_core as core
import resources

IO_BLOCK = core.IO_BLOCK


def _defaults(args, tools):
    info = resources.detect(".", getattr(args, "chunk_size", core.CHUNK_SIZE))
    threads = args.threads or info["derived"]["threads_default"]
    batch = args.batch_chunks or info["derived"]["batch_chunks_default"]
    return threads, batch


def cmd_compress(args):
    tools = resources.detect_tools()
    threads, batch = _defaults(args, tools)
    backend = "lzma_fast" if args.fast else "lzma_extreme"
    if args.backend == "zstd":
        backend = "zstd_12" if args.fast else "zstd_19"

    if not core.HAS_NUMPY:
        print("note: numpy not found, using the pure-Python LEB128 path "
              "(much slower on large files) -- pip install numpy", file=sys.stderr)

    orig_size = os.path.getsize(args.input)
    mb = orig_size / (1024 * 1024)

    def progress(done_bytes, elapsed):
        done_mb = done_bytes / (1024 * 1024)
        print(f"  ... tokenized+fed {done_mb:.0f}/{mb:.0f} MB "
              f"({done_mb / max(elapsed, 1e-9):.1f} MB/s input-side; compressor may "
              f"still be draining its own backlog)", flush=True)

    stats = core.compress_file(
        args.input, args.output,
        tokenizer="o200k_base", packing="leb128", backend=backend,
        transport="subprocess_cli", layout="library_batch",
        threads=threads, chunk_size=core.CHUNK_SIZE, batch_chunks=batch,
        tools=tools, progress=None if args.quiet else progress)

    if not args.quiet:
        print(f"input:              {args.input} ({stats['orig_len']:,} bytes, "
              f"{mb:.2f} MB)")
        print(f"tokenizer:          o200k_base")
        print(f"tokens:             {stats['token_count']:,}")
        print(f"backend:            {backend} via subprocess_cli "
              f"(threads={threads}, numpy={core.HAS_NUMPY})")
        print(f"output:             {args.output} ({stats['compressed_bytes']:,} bytes)")
        print(f"ratio:              {stats['ratio']:.3f}x")
        print(f"total time:         {stats['total_time_s']:.2f}s "
              f"({mb / max(stats['total_time_s'], 1e-9):.1f} MB/s)")
    return stats


def cmd_decompress(args):
    tools = resources.detect_tools()
    threads = args.threads or (os.cpu_count() or 1)
    res = core.decompress_file(args.input, args.output, threads, tools=tools)
    mb = res["orig_len"] / (1024 * 1024)
    print(f"decompressed:       {args.output} ({res['decompressed_len']:,} bytes)")
    if res["round_trip_verified"]:
        print("integrity:          OK (sha256 verified, byte-exact, streamed)")
    else:
        for e in res["errors"]:
            print(f"integrity:          FAILED -- {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"total time:         {res['decompress_time_s']:.2f}s "
          f"({mb / max(res['decompress_time_s'], 1e-9):.1f} MB/s)")
    return res


def stream_compress_size(input_path, argv):
    t0 = time.perf_counter()
    with open(input_path, "rb") as in_f:
        proc = subprocess.Popen(argv, stdin=in_f, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        total = 0
        while True:
            block = proc.stdout.read(IO_BLOCK)
            if not block:
                break
            total += len(block)
        rc = proc.wait()
        if rc != 0:
            stderr = proc.stderr.read().decode("utf-8", errors="replace") \
                if proc.stderr else ""
            raise RuntimeError(f"{argv[0]} exited with code {rc}: {stderr}")
    return total, time.perf_counter() - t0


def cmd_bench(args):
    tools = resources.detect_tools()
    threads, batch = _defaults(args, tools)
    orig_size = os.path.getsize(args.input)
    mb = orig_size / (1024 * 1024)
    backend = "lzma_fast" if args.fast else "lzma_extreme"

    print(f"benchmarking {args.input} ({orig_size:,} bytes, {mb:.2f} MB, "
          f"threads={threads}, numpy={core.HAS_NUMPY}, fast={args.fast})\n")
    if not args.fast:
        print("note: using the extreme LZMA2 preset (9e) -- this is deliberately slow "
              "(~1.5 MB/s per thread is normal on this machine). Pass --fast for a "
              "quick sanity pass, reserve this for final numbers.\n")

    def run_and_report(name, fn):
        print(f"[{time.strftime('%H:%M:%S')}] running: {name} ...", flush=True)
        size, elapsed = fn()
        ratio = orig_size / size if size else float("inf")
        print(f"[{time.strftime('%H:%M:%S')}] done:    {name} -> {size:,} bytes, "
              f"{ratio:.3f}x, {elapsed:.2f}s ({mb / max(elapsed, 1e-9):.1f} MB/s)\n",
              flush=True)
        return (name, size, elapsed)

    results = []
    tmp_dir = tempfile.mkdtemp(prefix="parmar_bench_")
    try:
        parmar_out = os.path.join(tmp_dir, "out.parmar")

        def run_parmar():
            s = core.compress_file(
                args.input, parmar_out, "o200k_base", "leb128", backend,
                "subprocess_cli", "library_batch", threads, core.CHUNK_SIZE, batch,
                tools=tools)
            return s["compressed_bytes"], s["total_time_s"]

        results.append(run_and_report(
            f"parmar (o200k_base + LEB128 + {backend})", run_parmar))

        raw = [("raw gzip -9", "gzip", ["-9", "-c"]),
               ("raw zstd multi-thread", "zstd",
                [f"-T{threads}", f"-{'12' if args.fast else '19'}", "--long=27", "-c"]),
               ("raw xz multi-thread", "xz", None)]
        for name, tool, tail in raw:
            entry = tools.get(tool)
            if not entry or not entry["available"]:
                print(f"note: {tool} not found on PATH or in any well-known install "
                      f"dir, skipping '{name}'\n")
                continue
            if tool == "xz":
                argv = core.compressor_argv(backend, threads, tools)
            else:
                argv = [entry["path"]] + tail
            results.append(run_and_report(
                name, lambda a=argv: stream_compress_size(args.input, a)))

        if args.full_baselines and tools["xz"]["available"]:
            argv = core.compressor_argv(backend, 1, tools)
            results.append(run_and_report(
                "raw xz single-thread (slow, --full-baselines)",
                lambda: stream_compress_size(args.input, argv)))
        elif not args.full_baselines:
            print("skipping raw xz single-thread baseline (slowest config by design; "
                  "pass --full-baselines to include it)\n")

        print(f"{'config':<44}{'size (bytes)':>16}{'ratio':>10}{'time (s)':>10}")
        for name, size, elapsed in results:
            ratio = orig_size / size if size else float("inf")
            print(f"{name:<44}{size:>16,}{ratio:>9.3f}x{elapsed:>10.2f}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def build_parser():
    p = argparse.ArgumentParser(
        description="parmar: streaming subword-domain compression")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compress")
    c.add_argument("input")
    c.add_argument("output")
    c.add_argument("--backend", choices=["lzma", "zstd"], default="lzma")
    c.add_argument("--threads", type=int, default=None)
    c.add_argument("--batch-chunks", type=int, default=None,
                   help="number of 2MB text chunks tokenized per batch "
                        "(bounds peak memory)")
    c.add_argument("--fast", action="store_true",
                   help="use a much faster LZMA2/zstd profile at some ratio cost")
    c.add_argument("--quiet", action="store_true")
    c.set_defaults(func=cmd_compress)

    d = sub.add_parser("decompress")
    d.add_argument("input")
    d.add_argument("output")
    d.add_argument("--threads", type=int, default=None)
    d.set_defaults(func=cmd_decompress)

    b = sub.add_parser("bench")
    b.add_argument("input")
    b.add_argument("--threads", type=int, default=None)
    b.add_argument("--batch-chunks", type=int, default=None)
    b.add_argument("--fast", action="store_true")
    b.add_argument("--full-baselines", action="store_true",
                   help="also run the single-threaded raw xz baseline "
                        "(slowest config, off by default)")
    b.set_defaults(func=cmd_bench)

    f = sub.add_parser("selftest", help="run the LEB128/fixed_u16 property test")
    f.add_argument("--cases", type=int, default=50_000)
    f.set_defaults(func=lambda a: core.run_fuzz(a.cases))

    return p


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
