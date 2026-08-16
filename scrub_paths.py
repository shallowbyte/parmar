#!/usr/bin/env python3
"""Rewrite absolute corpus paths in results files to repo-relative ones.

Results rows record the corpus path so `rerun-cell` can find it again. On a local
run that is an absolute path containing the operator's home directory, which has no
business being in a published results file. This rewrites it to the repo-relative
form, which is also what `rerun-cell` should be given when someone else reproduces
the run.

Idempotent, and safe to run repeatedly.
"""
import argparse
import glob
import json
import os
import re
import sys

ap = argparse.ArgumentParser()
ap.add_argument("paths", nargs="*", default=["results/*.jsonl"])
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()

files = []
for pat in (args.paths or ["results/*.jsonl"]):
    files.extend(glob.glob(pat))

CORPUS_RE = re.compile(r"^.*[\\/](corpus[\\/][^\\/]+)$")
changed_total = 0

for path in sorted(files):
    out, changed = [], 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            c = r.get("corpus")
            if isinstance(c, str):
                m = CORPUS_RE.match(c)
                if m:
                    rel = "./" + m.group(1).replace("\\", "/")
                    if rel != c:
                        r["corpus"] = rel
                        changed += 1
            # work_dir/traceback can also carry absolute paths
            for k in ("traceback", "error"):
                v = r.get(k)
                if isinstance(v, str) and os.path.sep in v:
                    r[k] = re.sub(r"[A-Za-z]:\\Users\\[^\\\"']+\\", "<path>/", v)
            out.append(r)
    print(f"{path}: {changed} corpus paths rewritten ({len(out)} rows)")
    changed_total += changed
    if not args.dry_run and changed:
        with open(path, "w", encoding="utf-8") as fh:
            for r in out:
                fh.write(json.dumps(r, default=str) + "\n")

print(f"total rewritten: {changed_total}")
sys.exit(0)
