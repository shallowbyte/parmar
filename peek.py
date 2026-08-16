#!/usr/bin/env python3
"""Quick console view of an in-progress sweep. Not part of the deliverable set."""
import json
import sys
from collections import defaultdict

path = sys.argv[1] if len(sys.argv) > 1 else "results/sweep_64mb.jsonl"
rows, seen = [], {}
for line in open(path, encoding="utf-8"):
    line = line.strip()
    if line:
        r = json.loads(line)
        seen[r["row_id"]] = r
rows = list(seen.values())

ok = [r for r in rows if r.get("round_trip_verified")]
bad = [r for r in rows if not r.get("round_trip_verified")]
print(f"{len(ok)}/{len(rows)} round-trip verified, {len(bad)} failed\n")

for r in bad:
    err = str(r.get("error"))[:200]
    print(f"  FAIL {r['tokenizer']}/{r['packing']}/{r['backend']}/"
          f"{r['backend_transport']}/{r['tokenization_layout']} "
          f"t={r['threads']}\n       {err}")
if bad:
    print()

g = [r for r in ok if r["cell_kind"] == "ratio_grid"]
if g:
    print(f"ratio grid ({len(g)} cells), best ratio first:")
    print(f"  {'ratio':<9}{'tokenizer':<13}{'packing':<11}{'backend':<20}"
          f"{'MB/s':>8}{'rss':>8}")
    for r in sorted(g, key=lambda x: -x["ratio"]):
        print(f"  {r['ratio']:<9.4f}{r['tokenizer']:<13}{r['packing']:<11}"
              f"{r['backend']:<20}{r.get('throughput_mbps') or 0:>8.2f}"
              f"{r.get('peak_rss_mb') or 0:>8.0f}")

    print("\n  parmar vs raw, per backend:")
    raw = {r["backend"]: r["ratio"] for r in g if r["tokenizer"] == "none"}
    best = defaultdict(lambda: (None, -1))
    for r in g:
        if r["tokenizer"] == "none":
            continue
        if r["ratio"] > best[r["backend"]][1]:
            best[r["backend"]] = (f"{r['tokenizer']}+{r['packing']}", r["ratio"])
    for b in sorted(best):
        if b in raw:
            lbl, val = best[b]
            d = val - raw[b]
            print(f"    {b:<20} raw={raw[b]:.4f}  best parmar={val:.4f} ({lbl})  "
                  f"gap={d:+.4f}  ({d / raw[b] * 100:+.2f}%)")

ofat = [r for r in ok if r["cell_kind"].startswith("ofat")]
if ofat:
    print(f"\nOFAT cells done: {len(ofat)}")
    kinds = defaultdict(int)
    for r in ofat:
        kinds[r["cell_kind"]] += 1
    for k in sorted(kinds):
        print(f"    {k:<22}{kinds[k]}")
