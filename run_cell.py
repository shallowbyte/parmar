#!/usr/bin/env python3
"""Execute exactly one matrix cell, in its own process.

Invoked by matrix.py as a subprocess so that a crash or OOM in one configuration
cannot take down the sweep, so peak-RSS is measured against a clean process rather
than against whatever the previous cell left uncollected, and so resume is trivial.

Reads a JSON cell spec on stdin, writes a JSON result object to stdout. Anything the
pipeline prints for humans goes to stderr, so stdout stays parseable.

The compress step is always followed by an actual decompress with sha256/length/
token-count checks. A cell that does not round-trip reports its ratio, but reports
round_trip_verified=false with it, and the analysis excludes it from comparisons.
"""

import json
import os
import sys
import time
import traceback

import parmar_core as core
import resources


def run(spec):
    tools = resources.detect_tools()
    out_dir = spec["work_dir"]
    os.makedirs(out_dir, exist_ok=True)
    archive = os.path.join(out_dir, f"cell_{spec['row_id']}.parmar")

    result = {
        "row_id": spec["row_id"],
        "status": "failed",
        "error": None,
        "round_trip_verified": False,
    }

    try:
        t_start = time.perf_counter()
        c = core.compress_file(
            input_path=spec["corpus"],
            output_path=archive,
            tokenizer=spec["tokenizer"],
            packing=spec["packing"],
            backend=spec["backend"],
            transport=spec["backend_transport"],
            layout=spec["tokenization_layout"],
            threads=spec["threads"],
            chunk_size=spec["chunk_size"],
            batch_chunks=spec["batch_chunks"],
            tools=tools,
        )
        mb = c["orig_len"] / (1024 * 1024)
        result.update({
            "corpus_bytes": c["orig_len"],
            "token_count": c["token_count"],
            "compressed_bytes": c["compressed_bytes"],
            "ratio": c["ratio"],
            "tokenize_time_s": round(c["tokenize_time_s"], 4),
            "pack_time_s": round(c["pack_time_s"], 4),
            "compress_time_s": round(c["compress_time_s"], 4),
            "total_time_s": round(c["total_time_s"], 4),
            "tokenizer_startup_s": round(c["tokenizer_startup_s"], 4),
            "throughput_mbps": round(mb / max(c["total_time_s"], 1e-9), 3),
            "compress_sha256": c["sha256"],
            "packed_bytes": c["packed_bytes"],
            "unsafe_boundary_cuts": c["unsafe_boundary_cuts"],
        })

        emit = spec.get("emit_decompressed")
        d = core.decompress_file(
            archive,
            os.path.join(out_dir, f"cell_{spec['row_id']}.out") if emit else None,
            spec["threads"], tools=tools)
        result.update({
            "decompress_time_s": round(d["decompress_time_s"], 4),
            "decompress_throughput_mbps": round(
                mb / max(d["decompress_time_s"], 1e-9), 3),
            "round_trip_verified": d["round_trip_verified"],
            "sha256_match": d["sha256_match"],
            "length_match": d["length_match"],
            "token_count_match": d["token_count_match"],
            "wall_time_s": round(time.perf_counter() - t_start, 4),
        })
        if d["errors"]:
            result["error"] = "; ".join(d["errors"])
        result["status"] = "done" if d["round_trip_verified"] else "failed"

    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()
        result["status"] = "failed"
    finally:
        if not spec.get("keep_archive") and os.path.exists(archive):
            try:
                os.unlink(archive)
            except OSError:
                pass
        leftover = os.path.join(out_dir, f"cell_{spec['row_id']}.out")
        if not spec.get("keep_archive") and os.path.exists(leftover):
            try:
                os.unlink(leftover)
            except OSError:
                pass

    return result


def main():
    spec = json.loads(sys.stdin.read())
    result = run(spec)
    sys.stdout.write(json.dumps(result))
    sys.stdout.flush()
    return 0 if result["status"] == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
