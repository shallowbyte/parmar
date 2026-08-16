#!/usr/bin/env python3
"""Drop result rows invalidated by a code change, so they re-run on the next sweep.

Used once, to remove in-process LZMA rows measured before the lzma_fast filter-spec
fix (the in-process filters did not match the preset handed to the xz CLI). Kept in
the tree because the same need recurs whenever a backend definition changes: a stale
row would otherwise be skipped forever by resume.
"""
import argparse
import json
import shutil

ap = argparse.ArgumentParser()
ap.add_argument("results")
ap.add_argument("--backend-prefix", default="lzma")
ap.add_argument("--transport", default="in_process_binding")
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()

kept, dropped = [], []
with open(args.results, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if (str(r.get("backend", "")).startswith(args.backend_prefix)
                and r.get("backend_transport") == args.transport):
            dropped.append(r)
        else:
            kept.append(r)

print(f"{len(kept)} kept, {len(dropped)} dropped")
for r in dropped:
    print(f"  drop {r['row_id']} {r['tokenizer']}/{r['packing']}/{r['backend']}/"
          f"{r['backend_transport']}")
if args.dry_run:
    raise SystemExit(0)

shutil.copy(args.results, args.results + ".bak")
with open(args.results, "w", encoding="utf-8") as fh:
    for r in kept:
        fh.write(json.dumps(r, default=str) + "\n")
print(f"rewrote {args.results} (backup at {args.results}.bak)")
