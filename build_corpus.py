#!/usr/bin/env python3
"""PG-19 corpus builder for the parmar scale sweep (handoff Section 4).

Dataset: deepmind/pg19 (Apache 2.0). Rae et al. 2019, "Compressive Transformers for
Long-Range Sequence Modelling", arXiv:1911.05507.

WHY THIS DOES NOT USE `datasets.load_dataset`
---------------------------------------------
The handoff specifies
    datasets.load_dataset("deepmind/pg19", split="train", streaming=True)
That cannot work as written, which was only discoverable by actually querying the Hub:

  * The `deepmind/pg19` repo contains exactly six files -- `.gitattributes`,
    `README.md`, `pg19.py`, and three `data/*_files.txt` lists. There is no parquet
    and no arrow.
  * Its `refs/convert/parquet` branch holds only `README.md`, `dataset_infos.json`
    and a copy of the script: the Hub's automatic parquet conversion never produced
    data for this dataset, so the usual script-free fallback does not exist.
  * `pg19.py` is a `GeneratorBasedBuilder` that downloads each book from
    `https://storage.googleapis.com/deepmind-gutenberg/`. Loading scripts were
    removed outright in `datasets` 3.0, so this path additionally requires pinning a
    deprecated major version and passing `trust_remote_code=True`.

The books themselves are plain text on public GCS and the authoritative file list is
in the repo, so this fetches them directly. That keeps every requirement of Section
4.1 -- document-boundary accumulation, per-tier checkpoints, recorded
sha256/doc-count/byte-count, fixed-seed shuffle -- while dropping a heavyweight
dependency and allowing parallel fetch (measured 3.5 MB/s at 64 workers here versus
~0.9 MB/s for a sequential stream).

ORDERING
--------
Documents are shuffled once with a fixed seed and then accumulated strictly in that
shuffled order. Downloads run in parallel but are reassembled in order via a bounded
sliding window, so the produced corpus is byte-identical regardless of the worker
count or of which request happens to finish first. This is what makes the recorded
sha256 a meaningful reproducibility check rather than a record of one lucky race.
"""

import argparse
import hashlib
import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

FILE_LIST_URL = ("https://huggingface.co/datasets/deepmind/pg19/raw/main/"
                 "data/train_files.txt")
ASSET_ROOT = "https://storage.googleapis.com/deepmind-gutenberg/"
SHUFFLE_SEED = 20240517
DEFAULT_WORKERS = 64
RETRIES = 5

TIERS = {
    "64MB": 64 * 1024 ** 2,
    "256MB": 256 * 1024 ** 2,
    "1GB": 1024 ** 3,
    "4GB": 4 * 1024 ** 3,
    "8GB": 8 * 1024 ** 3,
}
TIER_ORDER = ["64MB", "256MB", "1GB", "4GB", "8GB"]

# A single blank line between books. Document boundaries are never split, so each
# tier file is a complete standalone corpus rather than a prefix of the next one
# (handoff 4.1 point 3). The separator is counted in the tier's byte budget.
DOC_SEPARATOR = b"\n\n"


def tier_filename(tier):
    return f"pg19_{tier.lower()}.txt"


def meta_filename(tier):
    return f"pg19_{tier.lower()}.meta.json"


def fetch_url(url, timeout=180):
    last = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "parmar-corpus/1"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as e:
            last = e
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                raise
            time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"failed to fetch {url} after {RETRIES} attempts: {last}")


def load_file_list():
    raw = fetch_url(FILE_LIST_URL).decode("utf-8")
    files = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if not files:
        raise RuntimeError("train_files.txt came back empty")
    return files


def ordered_parallel_fetch(paths, workers, window):
    """Yield (path, bytes) strictly in `paths` order, fetching up to `window` ahead.

    A plain `executor.map` would work but would queue every remaining book at once;
    the bounded window keeps at most `window` book bodies (~400KB each) resident, so
    peak memory does not scale with the tier size.
    """
    with ThreadPoolExecutor(max_workers=workers) as ex:
        inflight = {}
        nxt = 0
        for i in range(min(window, len(paths))):
            inflight[i] = ex.submit(fetch_url, ASSET_ROOT + paths[i])
            nxt = i + 1
        cursor = 0
        while cursor < len(paths):
            fut = inflight.pop(cursor)
            try:
                yield paths[cursor], fut.result()
            except Exception as exc:
                print(f"  ! skipping {paths[cursor]}: {type(exc).__name__}: {exc}",
                      file=sys.stderr, flush=True)
                yield paths[cursor], None
            cursor += 1
            if nxt < len(paths):
                inflight[nxt] = ex.submit(fetch_url, ASSET_ROOT + paths[nxt])
                nxt += 1


def verify_tier(out_dir, tier):
    """Return the recorded metadata if the tier is already built and intact."""
    fp = os.path.join(out_dir, tier_filename(tier))
    mp = os.path.join(out_dir, meta_filename(tier))
    if not (os.path.exists(fp) and os.path.exists(mp)):
        return None
    with open(mp) as fh:
        meta = json.load(fh)
    if os.path.getsize(fp) != meta.get("bytes"):
        print(f"  ! {tier}: size on disk {os.path.getsize(fp):,} != recorded "
              f"{meta.get('bytes'):,}; rebuilding", flush=True)
        return None
    sha = hashlib.sha256()
    with open(fp, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 22), b""):
            sha.update(block)
    if sha.hexdigest() != meta.get("sha256"):
        print(f"  ! {tier}: sha256 mismatch; rebuilding", flush=True)
        return None
    return meta


def build(out_dir, tiers, workers, window, seed=SHUFFLE_SEED):
    os.makedirs(out_dir, exist_ok=True)
    wanted = sorted(tiers, key=lambda t: TIERS[t])
    todo = []
    for tier in wanted:
        existing = verify_tier(out_dir, tier)
        if existing:
            print(f"  {tier:<6} already built and verified "
                  f"({existing['bytes']:,} bytes, {existing['documents']:,} docs)")
        else:
            todo.append(tier)
    if not todo:
        print("all requested tiers already present and verified; nothing to do")
        return

    largest = todo[-1]
    target_bytes = TIERS[largest]
    print(f"\nbuilding up to {largest} ({target_bytes:,} bytes) in one pass; "
          f"checkpoints at: {', '.join(todo)}")

    print("fetching authoritative file list ...", flush=True)
    files = load_file_list()
    print(f"  {len(files):,} documents in the pg19 train split")
    random.Random(seed).shuffle(files)
    print(f"  shuffled with fixed seed {seed}")

    # Open every tier file that still needs building; each gets the same byte stream
    # up to its own target, then closes at the next document boundary past it.
    handles, shas, counts, sizes = {}, {}, {}, {}
    for t in todo:
        handles[t] = open(os.path.join(out_dir, tier_filename(t)), "wb")
        shas[t] = hashlib.sha256()
        counts[t] = 0
        sizes[t] = 0
    open_tiers = list(todo)

    total_bytes = 0
    docs_used = 0
    docs_seen = 0
    skipped = 0
    t0 = time.perf_counter()
    last_report = t0

    try:
        for path, body in ordered_parallel_fetch(files, workers, window):
            docs_seen += 1
            if body is None:
                skipped += 1
                continue
            try:
                body.decode("utf-8")
            except UnicodeDecodeError as e:
                print(f"  ! {path} is not valid UTF-8 ({e}); skipping", file=sys.stderr)
                skipped += 1
                continue

            record = body if body.endswith(b"\n") else body + b"\n"
            record += DOC_SEPARATOR
            docs_used += 1

            still_open = []
            for t in open_tiers:
                handles[t].write(record)
                shas[t].update(record)
                sizes[t] += len(record)
                counts[t] += 1
                if sizes[t] >= TIERS[t]:
                    handles[t].close()
                    meta = {
                        "tier": t,
                        "target_bytes": TIERS[t],
                        "bytes": sizes[t],
                        "documents": counts[t],
                        "sha256": shas[t].hexdigest(),
                        "shuffle_seed": seed,
                        "source": "deepmind/pg19 train split via " + ASSET_ROOT,
                        "file_list": FILE_LIST_URL,
                        "doc_separator": DOC_SEPARATOR.decode(),
                        "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "note": ("cut at a document boundary past the target, so this "
                                 "file is a complete standalone corpus, not a "
                                 "truncated prefix of a larger tier"),
                    }
                    with open(os.path.join(out_dir, meta_filename(t)), "w") as fh:
                        json.dump(meta, fh, indent=2)
                    print(f"\n  [OK] {t:<6} {sizes[t]:,} bytes, {counts[t]:,} docs, "
                          f"sha256={meta['sha256'][:16]}...", flush=True)
                else:
                    still_open.append(t)
            open_tiers = still_open
            total_bytes += len(record)

            if not open_tiers:
                break

            now = time.perf_counter()
            if now - last_report >= 10.0:
                mb = total_bytes / 1024 ** 2
                el = now - t0
                pend = open_tiers[0]
                print(f"    {mb:8.1f} MB / {docs_used:,} docs  "
                      f"({mb / el:.2f} MB/s)  next checkpoint: {pend} at "
                      f"{TIERS[pend] / 1024 ** 2:.0f} MB", flush=True)
                last_report = now
    finally:
        for t in open_tiers:
            handles[t].close()

    if open_tiers:
        print(f"\n! ran out of documents before reaching: {', '.join(open_tiers)}",
              file=sys.stderr)
        print(f"! the pg19 train split provided {total_bytes:,} bytes across "
              f"{docs_used:,} usable documents", file=sys.stderr)
        for t in open_tiers:
            os.unlink(os.path.join(out_dir, tier_filename(t)))
            print(f"! removed incomplete {tier_filename(t)}", file=sys.stderr)

    el = time.perf_counter() - t0
    print(f"\ndone: {total_bytes / 1024 ** 2:.1f} MB, {docs_used:,} documents used, "
          f"{skipped} skipped, {docs_seen:,} seen, in {el / 60:.1f} min "
          f"({total_bytes / 1024 ** 2 / max(el, 1e-9):.2f} MB/s)")


def cmd_verify(out_dir, tiers):
    ok = True
    for tier in tiers:
        fp = os.path.join(out_dir, tier_filename(tier))
        if not os.path.exists(fp):
            print(f"  {tier:<6} MISSING")
            ok = False
            continue
        meta = verify_tier(out_dir, tier)
        if meta is None:
            print(f"  {tier:<6} FAILED checksum/size verification")
            ok = False
            continue

        # Validate the tail: the file must end at a real document boundary and the
        # whole thing must decode as UTF-8 (checked incrementally so a 4GB tier does
        # not need 4GB of RAM to verify).
        import codecs
        dec = codecs.getincrementaldecoder("utf-8")()
        tail = b""
        with open(fp, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 22), b""):
                dec.decode(block)
                tail = block[-64:]
        try:
            dec.decode(b"", final=True)
            utf8_ok = True
        except UnicodeDecodeError as e:
            utf8_ok = False
            print(f"  {tier:<6} INVALID UTF-8 at the tail: {e}")
        boundary_ok = tail.endswith(DOC_SEPARATOR)
        print(f"  {tier:<6} OK  {meta['bytes']:,} bytes, {meta['documents']:,} docs, "
              f"sha256={meta['sha256'][:16]}...  utf8={utf8_ok} "
              f"ends_at_doc_boundary={boundary_ok}")
        ok = ok and utf8_ok and boundary_ok
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="Build PG-19 corpus tiers (handoff Section 4)")
    ap.add_argument("--tiers", default="64MB",
                    help="comma-separated tiers: " + ",".join(TIER_ORDER))
    ap.add_argument("--out", default="./corpus/")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--window", type=int, default=None,
                    help="max books held in flight (default: 2x workers)")
    ap.add_argument("--seed", type=int, default=SHUFFLE_SEED)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    tiers = [t.strip() for t in args.tiers.split(",") if t.strip()]
    bad = [t for t in tiers if t not in TIERS]
    if bad:
        ap.error(f"unknown tier(s) {bad}; choose from {TIER_ORDER}")

    if args.verify_only:
        raise SystemExit(cmd_verify(args.out, tiers))

    window = args.window or args.workers * 2
    build(args.out, tiers, args.workers, window, args.seed)
    print("\nverification:")
    raise SystemExit(cmd_verify(args.out, tiers))


if __name__ == "__main__":
    main()
