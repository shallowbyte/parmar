#!/usr/bin/env python3
"""parmar stress-test matrix harness.

Subcommands
  smoke              one config, smallest tier, fast profile -- the pre-flight check
  verify-leb128      packing property/fuzz test
  verify-boundaries  chunk-boundary differential test, delegated to
                     verify_boundaries.py so it stays a standalone blocking script
  plan               print the generated cells and the drop log without running
  sweep              run the matrix, resumable
  rerun-cell         re-execute exactly one cell by row id

MATRIX SHAPE -- a documented deviation from the design spec
-------------------------------------------------------
The full axis list taken as a literal cartesian product give ~8,100 valid cells per
corpus tier (7 tokenizer/packing pairs x ~7.3 backends x 2 transports x 3 layouts x
3 chunk sizes x 3 batch sizes x 3 thread counts). At this machine's measured
throughput that is weeks per tier, so the product is split into two blocks:

  ratio grid  Full cross of the axes that determine compression ratio
              (tokenizer x packing x backend), at fixed baseline performance
              settings. 51 cells. Answers questions 1 and 2 below and produces
              the ratio-vs-scale plot, which is the harness's central deliverable.

  perf OFAT   One-factor-at-a-time around the same baseline over the axes that
              should only affect speed (threads, layout, transport, chunk size,
              batch size), on representative backends. Answers questions 3 and 4.

The separation rests on the design spec's own claim that chunk size must not affect
ratio if boundary-safety holds. That is verified independently by
verify_boundaries.py rather than assumed, and the OFAT block still records ratio for
every cell -- so if a performance axis does move ratio, it shows up as a
contradiction in the results rather than being averaged away.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time

import parmar_core as core
import resources

RESULTS_FIELDS = [
    "row_id", "cell_kind", "corpus_tier", "corpus_bytes", "corpus_sha256",
    "tokenizer", "packing", "backend", "backend_profile", "backend_transport",
    "tokenization_layout", "chunk_size", "batch_chunks", "threads",
    "tokenize_time_s", "pack_time_s", "compress_time_s", "total_time_s",
    "throughput_mbps", "compressed_bytes", "ratio", "token_count",
    "peak_rss_mb", "decompress_time_s", "decompress_throughput_mbps",
    "round_trip_verified", "sha256_match", "token_count_match", "length_match",
    "tokenizer_startup_s", "error", "status", "started_utc", "finished_utc",
]

SIZE_SUFFIX = {"KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}

CHUNK_SIZES = [1024 ** 2, 2 * 1024 ** 2, 4 * 1024 ** 2]
BASELINE_CHUNK = 2 * 1024 ** 2

# Representative selections for the OFAT block. Chosen to span the two backend
# families, both profiles, and all three packing schemes, without multiplying out.
OFAT_BACKENDS = ["lzma_extreme", "lzma_fast", "zstd_19", "zstd_12"]
OFAT_PAIRS = [("o200k_base", "leb128"), ("none", "raw_utf8"),
              ("r50k_base", "fixed_u16")]


def parse_size(s):
    s = str(s).strip().upper()
    for suf, mult in SIZE_SUFFIX.items():
        if s.endswith(suf):
            return int(float(s[:-len(suf)]) * mult)
    return int(s)


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


# --------------------------------------------------------------------------------
# Corpus identity
# --------------------------------------------------------------------------------

def corpus_info(path):
    meta_path = os.path.splitext(path)[0] + ".meta.json"
    if os.path.exists(meta_path):
        with open(meta_path) as fh:
            meta = json.load(fh)
        return {"tier": meta.get("tier", os.path.basename(path)),
                "bytes": meta.get("bytes", os.path.getsize(path)),
                "sha256": meta.get("sha256")}
    sha = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 22), b""):
            sha.update(block)
    return {"tier": os.path.basename(path), "bytes": os.path.getsize(path),
            "sha256": sha.hexdigest()}


# --------------------------------------------------------------------------------
# Cell generation + validity filtering (5.1 / 5.2)
# --------------------------------------------------------------------------------

def vocab_of(tokenizer):
    if tokenizer == "none":
        return 0
    return core.EXPECTED_VOCAB[tokenizer]


def validity_drop_reason(tokenizer, packing, backend):
    """Handoff 5.2. Returns None if the combination is valid, else the reason."""
    if packing == "fixed_u16" and vocab_of(tokenizer) > core.FIXED_U16_MAX_VALUE + 1:
        return (f"packing=fixed_u16 requires vocab <= {core.FIXED_U16_MAX_VALUE + 1}; "
                f"{tokenizer} has {vocab_of(tokenizer)}")
    if packing == "raw_utf8" and tokenizer != "none":
        return "packing=raw_utf8 is only valid with tokenizer=none"
    if tokenizer == "none" and packing != "raw_utf8":
        return f"tokenizer=none has no token ids to pack as {packing}"
    if backend == "lzma_tuned_lp1pb1" and packing != "fixed_u16":
        return ("backend=lzma_tuned_lp1pb1 asserts a fixed 2-byte period; only "
                "meaningful with packing=fixed_u16")
    return None


def availability_drop_reason(backend, transport, tools, libs):
    b = core.BACKENDS[backend]
    tool_for = {"lzma": "xz", "zstd": "zstd", "gzip": "gzip", "bz2": "bzip2"}
    if transport == "subprocess_cli":
        name = tool_for[b.family]
        entry = tools.get(name)
        if not entry or not entry["available"]:
            return f"{name} CLI not found on PATH or in any well-known install dir"
        if b.family == "lzma" and not entry.get("supports_threading", True):
            return f"xz {entry.get('version')} does not support -T multithreading"
    else:
        if b.family == "zstd" and not libs["zstandard"]["available"]:
            return "zstandard package not installed; zstd in_process_binding needs it"
    return None


def make_cell(corpus, tokenizer, packing, backend, transport, layout, chunk_size,
              batch_chunks, threads, kind):
    cell = {
        "corpus": corpus["path"],
        "corpus_tier": corpus["tier"],
        "corpus_bytes": corpus["bytes"],
        "corpus_sha256": corpus["sha256"],
        "tokenizer": tokenizer,
        "packing": packing,
        "backend": backend,
        "backend_profile": core.BACKENDS[backend].profile,
        "backend_transport": transport,
        "tokenization_layout": layout,
        "chunk_size": chunk_size,
        "batch_chunks": batch_chunks,
        "threads": threads,
        "cell_kind": kind,
    }
    cell["row_id"] = row_id_for(cell)
    return cell


def row_id_for(cell):
    """Stable across runs and machines, so resume and rerun-cell agree on identity."""
    keys = ["corpus_tier", "tokenizer", "packing", "backend", "backend_transport",
            "tokenization_layout", "chunk_size", "batch_chunks", "threads"]
    canon = json.dumps({k: cell[k] for k in keys}, sort_keys=True)
    return hashlib.blake2b(canon.encode(), digest_size=6).hexdigest()


def generate_cells(corpus, profile, defaults, tools, libs, include_ofat=True,
                   thread_values=None, ofat_axes=None):
    """Returns (cells, dropped). Every dropped cell carries its reason (5.2)."""
    cells = []
    dropped = []
    seen = set()

    backends = list(core.BACKENDS)
    if profile == "fast":
        backends = [b for b in backends if core.BACKENDS[b].profile == "fast"]

    base_threads = defaults["threads_default"]
    base_batch = defaults["batch_chunks_default"]
    baseline = {
        "layout": "library_batch",
        "transport": "subprocess_cli",
        "chunk_size": BASELINE_CHUNK,
        "batch_chunks": base_batch,
        "threads": base_threads,
    }

    def add(tok, pack, backend, transport, layout, chunk, batch, threads, kind):
        reason = validity_drop_reason(tok, pack, backend)
        if reason:
            dropped.append({"tokenizer": tok, "packing": pack, "backend": backend,
                            "transport": transport, "reason": reason})
            return
        reason = availability_drop_reason(backend, transport, tools, libs)
        if reason:
            dropped.append({"tokenizer": tok, "packing": pack, "backend": backend,
                            "transport": transport, "reason": reason})
            return
        # tokenizer=none does no tokenization, so layout is not an axis for it.
        if tok == "none" and layout != "library_batch":
            dropped.append({"tokenizer": tok, "packing": pack, "backend": backend,
                            "transport": transport,
                            "reason": f"tokenization_layout={layout} is meaningless "
                                      f"with tokenizer=none (no tokenization step)"})
            return
        c = make_cell(corpus, tok, pack, backend, transport, layout, chunk, batch,
                      threads, kind)
        if c["row_id"] in seen:
            return
        seen.add(c["row_id"])
        cells.append(c)

    # --- ratio grid -------------------------------------------------------------
    # The full cartesian product is generated and then filtered, rather than only
    # the known-valid pairs being enumerated, so the drop log is real evidence that
    # the validity rules do what they claim -- including catching the case where
    # they wrongly drop something that should have run.
    for tok in core.TOKENIZERS:
        for pack in ("raw_utf8", "leb128", "fixed_u16"):
            for backend in backends:
                add(tok, pack, backend, baseline["transport"], baseline["layout"],
                    baseline["chunk_size"], baseline["batch_chunks"],
                    baseline["threads"], "ratio_grid")

    if not include_ofat:
        return cells, dropped

    # --- performance OFAT -------------------------------------------------------
    axes = ofat_axes or ["threads", "layout", "transport", "chunk_size", "batch_chunks"]
    thread_vals = thread_values if thread_values is not None else \
        sorted({1, 4, base_threads})

    ofat_backends = [b for b in OFAT_BACKENDS if b in backends]
    for tok, pack in OFAT_PAIRS:
        for backend in ofat_backends:
            if "threads" in axes:
                for th in thread_vals:
                    if th == baseline["threads"]:
                        continue
                    add(tok, pack, backend, baseline["transport"], baseline["layout"],
                        baseline["chunk_size"], baseline["batch_chunks"], th,
                        "ofat_threads")
            if "layout" in axes:
                for lay in core.TOKENIZATION_LAYOUTS:
                    if lay == baseline["layout"]:
                        continue
                    add(tok, pack, backend, baseline["transport"], lay,
                        baseline["chunk_size"], baseline["batch_chunks"],
                        baseline["threads"], "ofat_layout")
            if "transport" in axes:
                add(tok, pack, backend, "in_process_binding", baseline["layout"],
                    baseline["chunk_size"], baseline["batch_chunks"],
                    baseline["threads"], "ofat_transport")
            if "chunk_size" in axes:
                for cs in CHUNK_SIZES:
                    if cs == baseline["chunk_size"]:
                        continue
                    add(tok, pack, backend, baseline["transport"], baseline["layout"],
                        cs, baseline["batch_chunks"], baseline["threads"],
                        "ofat_chunk_size")
            if "batch_chunks" in axes:
                for mult in (0.5, 2.0):
                    bc = max(2, int(base_batch * mult))
                    if bc == baseline["batch_chunks"]:
                        continue
                    add(tok, pack, backend, baseline["transport"], baseline["layout"],
                        baseline["chunk_size"], bc, baseline["threads"],
                        "ofat_batch_chunks")

    return cells, dropped


# --------------------------------------------------------------------------------
# Execution with peak-RSS measurement
# --------------------------------------------------------------------------------

def _watch_rss(pid, stop_evt, out):
    """Poll the child process tree's RSS.

    resource.getrusage(RUSAGE_CHILDREN) is Unix-only and would not see the
    compressor grandchild's peak separately anyway, so the tree is sampled. If
    psutil is unavailable the field stays None rather than being guessed -- an
    invented number is worse than a missing one.
    """
    try:
        import psutil
    except ImportError:
        return
    try:
        proc = psutil.Process(pid)
    except Exception:
        return
    peak = 0
    while not stop_evt.is_set():
        try:
            total = proc.memory_info().rss
            for ch in proc.children(recursive=True):
                try:
                    total += ch.memory_info().rss
                except Exception:
                    pass
            peak = max(peak, total)
        except Exception:
            break
        stop_evt.wait(0.05)
    if peak:
        out["peak_rss_mb"] = round(peak / (1024 * 1024), 2)


def execute_cell(cell, work_dir, python_exe, timeout=None, keep_archive=False,
                 emit_decompressed=False):
    spec = dict(cell)
    spec["work_dir"] = work_dir
    spec["keep_archive"] = keep_archive
    spec["emit_decompressed"] = emit_decompressed

    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        [python_exe, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "run_cell.py")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=os.path.dirname(os.path.abspath(__file__)))

    rss = {}
    stop = threading.Event()
    watcher = threading.Thread(target=_watch_rss, args=(proc.pid, stop, rss),
                               daemon=True)
    watcher.start()
    try:
        out, err = proc.communicate(json.dumps(spec).encode(), timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        stop.set(); watcher.join(timeout=2)
        return {**cell, "status": "failed", "round_trip_verified": False,
                "error": f"cell exceeded timeout of {timeout}s",
                "started_utc": started,
                "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "wall_time_s": round(time.perf_counter() - t0, 3)}
    finally:
        stop.set()
        watcher.join(timeout=2)

    try:
        result = json.loads(out.decode() or "{}")
    except json.JSONDecodeError:
        result = {"status": "failed",
                  "error": f"child produced unparseable stdout: {out[:400]!r}"}

    if not result or result.get("status") is None:
        result = {"status": "failed",
                  "error": f"child exited {proc.returncode} with no result; "
                           f"stderr tail: {err.decode(errors='replace')[-500:]}"}

    row = {**cell, **result}
    row.update({
        "started_utc": started,
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "peak_rss_mb": rss.get("peak_rss_mb"),
    })
    if err and result.get("status") == "failed" and not result.get("error"):
        row["error"] = err.decode(errors="replace")[-500:]
    return row


# --------------------------------------------------------------------------------
# Results file (5.4 / 5.5)
# --------------------------------------------------------------------------------

def load_results(path):
    done, rows = {}, []
    if not os.path.exists(path):
        return done, rows
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append(row)
            if row.get("status") == "done" and row.get("round_trip_verified") is True:
                done[row["row_id"]] = row
    return done, rows


def append_result(path, row):
    """Append + fsync immediately; a killed sweep must never lose completed work."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    ordered = {k: row.get(k) for k in RESULTS_FIELDS}
    for k, v in row.items():
        if k not in ordered:
            ordered[k] = v
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(ordered, default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# --------------------------------------------------------------------------------
# Pre-flight estimate gate (8.4)
# --------------------------------------------------------------------------------

def estimate_sweep(cells, results_dir, corpus, free_bytes):
    """Extrapolate wall-clock and disk from throughput measured at smaller tiers."""
    prior = []
    if os.path.isdir(results_dir):
        for fn in os.listdir(results_dir):
            if fn.endswith(".jsonl"):
                _, rows = load_results(os.path.join(results_dir, fn))
                prior.extend(rows)

    by_backend = {}
    ratios = {}
    for r in prior:
        if not r.get("round_trip_verified"):
            continue
        key = (r.get("backend"), r.get("backend_transport"), r.get("threads"))
        tp = r.get("throughput_mbps")
        dtp = r.get("decompress_throughput_mbps")
        if tp:
            by_backend.setdefault(key, []).append((tp, dtp or tp))
        if r.get("ratio"):
            ratios.setdefault(r.get("backend"), []).append(r["ratio"])

    def median(xs):
        xs = sorted(xs)
        return xs[len(xs) // 2] if xs else None

    corpus_mb = corpus["bytes"] / (1024 * 1024)
    total_s = 0.0
    total_disk = 0
    unknown = 0
    for c in cells:
        key = (c["backend"], c["backend_transport"], c["threads"])
        samples = by_backend.get(key) or by_backend.get(
            (c["backend"], c["backend_transport"], None))
        if not samples:
            samples = [s for k, v in by_backend.items() if k[0] == c["backend"]
                       for s in v]
        if samples:
            ctp = median([s[0] for s in samples])
            dtp = median([s[1] for s in samples])
            total_s += corpus_mb / max(ctp, 1e-9) + corpus_mb / max(dtp, 1e-9)
        else:
            unknown += 1
        rs = ratios.get(c["backend"])
        r = median(rs) if rs else 3.0
        total_disk = max(total_disk, int(corpus["bytes"] / max(r, 0.1)))

    return {
        "cells": len(cells),
        "cells_without_prior_data": unknown,
        "est_wall_clock_s": total_s,
        "est_peak_extra_disk_bytes": total_disk,
        "free_disk_bytes": free_bytes,
        "prior_rows_used": len(prior),
    }


def print_estimate(est):
    print("-" * 74)
    print("PRE-FLIGHT ESTIMATE")
    print(f"  cells to run                 {est['cells']}")
    print(f"  cells with no prior timing   {est['cells_without_prior_data']} "
          f"(excluded from the time estimate)")
    hrs = est["est_wall_clock_s"] / 3600
    print(f"  estimated wall clock         {hrs:.2f} h "
          f"({est['est_wall_clock_s'] / 60:.0f} min), from {est['prior_rows_used']} "
          f"prior verified rows")
    print(f"  peak extra disk (1 archive)  {human(est['est_peak_extra_disk_bytes'])}")
    print(f"  free disk                    {human(est['free_disk_bytes'])}")
    if est["cells_without_prior_data"] == est["cells"]:
        print("  ! no prior throughput data at any tier; the time estimate is "
              "meaningless for this run")
    print("-" * 74)


# --------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------

def _setup(args):
    info = resources.detect(os.path.dirname(os.path.abspath(args.corpus)) or ".")
    corpus = corpus_info(args.corpus)
    corpus["path"] = os.path.abspath(args.corpus)
    return info, corpus


def cmd_plan(args):
    info, corpus = _setup(args)
    cells, dropped = generate_cells(
        corpus, args.profile, info["derived"], info["tools"], info["py_libs"],
        include_ofat=not args.no_ofat)
    print(f"corpus {corpus['tier']} ({corpus['bytes']:,} bytes) profile={args.profile}")
    print(f"\n{len(cells)} cells generated")
    kinds = {}
    for c in cells:
        kinds[c["cell_kind"]] = kinds.get(c["cell_kind"], 0) + 1
    for k, v in sorted(kinds.items()):
        print(f"  {k:<20} {v}")
    print(f"\n{len(dropped)} combinations dropped by validity/availability filtering:")
    seen = {}
    for d in dropped:
        seen.setdefault(d["reason"], 0)
        seen[d["reason"]] += 1
    for reason, n in sorted(seen.items(), key=lambda kv: -kv[1]):
        print(f"  [{n:>4}x] {reason}")
    if args.verbose:
        print("\ncells:")
        for c in cells:
            print(f"  {c['row_id']}  {c['cell_kind']:<18} {c['tokenizer']:<12}"
                  f"{c['packing']:<11}{c['backend']:<20}{c['backend_transport']:<20}"
                  f"{c['tokenization_layout']:<15}chunk={c['chunk_size'] >> 20}MB "
                  f"batch={c['batch_chunks']:<4}threads={c['threads']}")
    return 0


def cmd_smoke(args):
    info, corpus = _setup(args)
    print("running LEB128/fixed_u16 property test first ...")
    core.run_fuzz(5000)
    print()
    work = args.work_dir or os.path.join(os.path.dirname(corpus["path"]), "_work")
    cell = make_cell(corpus, "o200k_base", "leb128", "lzma_fast", "subprocess_cli",
                     "library_batch", BASELINE_CHUNK,
                     info["derived"]["batch_chunks_default"],
                     info["derived"]["threads_default"], "smoke")
    print(f"smoke cell {cell['row_id']}: o200k_base / leb128 / lzma_fast / "
          f"subprocess_cli, threads={cell['threads']}")
    t0 = time.perf_counter()
    row = execute_cell(cell, work, sys.executable)
    el = time.perf_counter() - t0
    print(f"\nstatus              {row['status']}")
    print(f"ratio               {row.get('ratio')}")
    print(f"compressed bytes    {row.get('compressed_bytes'):,}"
          if row.get("compressed_bytes") else "compressed bytes    -")
    print(f"throughput          {row.get('throughput_mbps')} MB/s")
    print(f"peak rss            {row.get('peak_rss_mb')} MB")
    print(f"round trip verified {row.get('round_trip_verified')}")
    if row.get("error"):
        print(f"error               {row['error']}")
    print(f"wall clock          {el:.1f}s")
    if args.results:
        append_result(args.results, row)
    return 0 if row.get("round_trip_verified") else 1


def cmd_verify_leb128(args):
    core.run_fuzz(args.cases)
    return 0


def cmd_verify_boundaries(args):
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "verify_boundaries.py")
    argv = [sys.executable, script, "--corpus", args.corpus,
            "--tokenizers", args.tokenizers, "--chunk-sizes", args.chunk_sizes]
    if args.sample_bytes:
        argv += ["--sample-bytes", args.sample_bytes]
    if args.skip_adversarial:
        argv.append("--skip-adversarial")
    return subprocess.call(argv)


def cmd_sweep(args):
    info, corpus = _setup(args)

    # Re-verify packing before every tier and before every resume,
    # rather than trusting a pass from an earlier process.
    print("pre-sweep packing property test ...")
    core.run_fuzz(args.fuzz_cases)
    print()

    cells, dropped = generate_cells(
        corpus, args.profile, info["derived"], info["tools"], info["py_libs"],
        include_ofat=not args.no_ofat,
        thread_values=[int(t) for t in args.threads.split(",")] if args.threads else None,
        ofat_axes=([a.strip() for a in args.ofat_axes.split(",") if a.strip()]
                   if args.ofat_axes else None))

    results_path = args.results or os.path.join(
        args.results_dir, f"sweep_{corpus['tier'].lower()}_{args.profile}.jsonl")
    done, _ = load_results(results_path)

    print(f"corpus     {corpus['tier']} ({corpus['bytes']:,} bytes, "
          f"sha256={(corpus['sha256'] or '?')[:16]}...)")
    print(f"profile    {args.profile}")
    print(f"results    {results_path}")
    print(f"cells      {len(cells)} planned, {len(dropped)} dropped by filtering")

    reasons = {}
    for d in dropped:
        reasons[d["reason"]] = reasons.get(d["reason"], 0) + 1
    for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"             dropped {n:>4}x: {reason}")

    todo = [c for c in cells if c["row_id"] not in done]
    print(f"           {len(done)} already done and verified -> "
          f"{len(todo)} to run\n")
    if not todo:
        print("nothing to do")
        return 0

    est = estimate_sweep(todo, args.results_dir, corpus,
                         info["disk"]["free_bytes"])
    print_estimate(est)
    if est["est_peak_extra_disk_bytes"] * 2 > info["disk"]["free_bytes"]:
        print("REFUSING: estimated archive size exceeds half the free disk.")
        return 2
    if args.confirm_estimate and not args.yes:
        try:
            reply = input("proceed? [y/N] ").strip().lower()
        except EOFError:
            reply = "n"
        if reply != "y":
            print("aborted at the estimate gate")
            return 1

    work = args.work_dir or os.path.join(os.path.dirname(corpus["path"]), "_work")
    os.makedirs(work, exist_ok=True)

    t_start = time.perf_counter()
    ok = failed = 0
    try:
        for i, cell in enumerate(todo, 1):
            label = (f"{cell['tokenizer']}/{cell['packing']}/{cell['backend']}/"
                     f"{cell['backend_transport']}/{cell['tokenization_layout']}"
                     f" c={cell['chunk_size'] >> 20}M b={cell['batch_chunks']} "
                     f"t={cell['threads']}")
            print(f"[{i}/{len(todo)}] {cell['row_id']} {cell['cell_kind']:<18} {label}",
                  flush=True)
            row = execute_cell(cell, work, sys.executable, timeout=args.cell_timeout,
                               keep_archive=args.keep_archives)
            append_result(results_path, row)
            if row.get("round_trip_verified"):
                ok += 1
                print(f"        -> {row.get('ratio', 0):.4f}x  "
                      f"{row.get('compressed_bytes', 0):,}B  "
                      f"{row.get('throughput_mbps')}MB/s  "
                      f"rss={row.get('peak_rss_mb')}MB  "
                      f"{row.get('wall_time_s', 0):.1f}s", flush=True)
            else:
                failed += 1
                print(f"        -> FAILED: {row.get('error')}", flush=True)
    except KeyboardInterrupt:
        print("\ninterrupted; completed cells are already on disk, rerun with "
              "--resume to continue", flush=True)
        return 130
    finally:
        if not args.keep_archives:
            shutil.rmtree(work, ignore_errors=True)

    el = time.perf_counter() - t_start
    print(f"\nsweep complete: {ok} verified, {failed} failed, in {el / 60:.1f} min")
    return 0 if failed == 0 else 1


def cmd_rerun_cell(args):
    _, rows = load_results(args.results)
    match = [r for r in rows if r.get("row_id") == args.row_id]
    if not match:
        print(f"no row with row_id={args.row_id} in {args.results}", file=sys.stderr)
        return 2
    row = match[-1]
    cell = {k: row[k] for k in
            ["corpus_tier", "corpus_bytes", "corpus_sha256", "tokenizer", "packing",
             "backend", "backend_profile", "backend_transport", "tokenization_layout",
             "chunk_size", "batch_chunks", "threads", "cell_kind", "row_id"]}
    cell["corpus"] = args.corpus or row.get("corpus")
    if not cell["corpus"] or not os.path.exists(cell["corpus"]):
        print(f"corpus path unknown or missing; pass --corpus", file=sys.stderr)
        return 2
    work = args.work_dir or "./_work"
    print(f"re-running {args.row_id}: {cell['tokenizer']}/{cell['packing']}/"
          f"{cell['backend']}/{cell['backend_transport']}")
    out = execute_cell(cell, work, sys.executable, keep_archive=args.keep_archives,
                       emit_decompressed=args.emit_decompressed)
    print(json.dumps({k: out.get(k) for k in RESULTS_FIELDS}, indent=2, default=str))
    if args.append:
        append_result(args.results, out)
    return 0 if out.get("round_trip_verified") else 1


def build_parser():
    p = argparse.ArgumentParser(description="parmar stress-test matrix")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--corpus", required=True)
        sp.add_argument("--work-dir", default=None)

    s = sub.add_parser("smoke", help="single config, fast profile, verified")
    add_common(s)
    s.add_argument("--results", default=None)
    s.set_defaults(func=cmd_smoke)

    v = sub.add_parser("verify-leb128", help="packing property/fuzz test (§8.3)")
    v.add_argument("--cases", type=int, default=50_000)
    v.set_defaults(func=cmd_verify_leb128)

    b = sub.add_parser("verify-boundaries", help="chunk-boundary differential (§8.2)")
    b.add_argument("--corpus", required=True)
    b.add_argument("--tokenizers",
                   default="o200k_base,cl100k_base,r50k_base,p50k_base")
    b.add_argument("--chunk-sizes", default="1MB,2MB,4MB")
    b.add_argument("--sample-bytes", default=None)
    b.add_argument("--skip-adversarial", action="store_true")
    b.set_defaults(func=cmd_verify_boundaries)

    pl = sub.add_parser("plan", help="print generated cells + drop log, run nothing")
    add_common(pl)
    pl.add_argument("--profile", choices=["fast", "full"], default="fast")
    pl.add_argument("--no-ofat", action="store_true")
    pl.add_argument("--verbose", action="store_true")
    pl.set_defaults(func=cmd_plan)

    w = sub.add_parser("sweep", help="run the matrix, resumable")
    add_common(w)
    w.add_argument("--profile", choices=["fast", "full"], default="fast")
    w.add_argument("--results", default=None)
    w.add_argument("--results-dir", default="./results")
    w.add_argument("--resume", action="store_true",
                   help="skip cells already done and round-trip-verified (default)")
    w.add_argument("--no-ofat", action="store_true",
                   help="ratio grid only; skip the performance OFAT block")
    w.add_argument("--threads", default=None,
                   help="comma-separated thread values for the OFAT threads axis")
    w.add_argument("--ofat-axes", default=None,
                   help="restrict the OFAT block to these axes, e.g. 'threads'. "
                        "Useful for getting the xz -T speedup curve at a large tier "
                        "without paying for the whole performance block.")
    w.add_argument("--confirm-estimate", action="store_true",
                   help="require interactive confirmation of the §8.4 estimate")
    w.add_argument("--yes", action="store_true", help="auto-confirm the estimate gate")
    w.add_argument("--cell-timeout", type=float, default=None)
    w.add_argument("--keep-archives", action="store_true")
    w.add_argument("--fuzz-cases", type=int, default=20_000)
    w.set_defaults(func=cmd_sweep)

    r = sub.add_parser("rerun-cell", help="re-execute one cell by row id")
    r.add_argument("--results", required=True)
    r.add_argument("--row-id", required=True)
    r.add_argument("--corpus", default=None)
    r.add_argument("--work-dir", default=None)
    r.add_argument("--keep-archives", action="store_true")
    r.add_argument("--emit-decompressed", action="store_true")
    r.add_argument("--append", action="store_true")
    r.set_defaults(func=cmd_rerun_cell)

    return p


def main():
    args = build_parser().parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
