#!/usr/bin/env python3
"""Analysis deliverables for the parmar sweep (handoff Section 7).

Produces, from whatever results have accumulated so far -- this works on a partial,
in-progress results set and does not require every tier to have finished:

  1. a merged CSV of every result row
  2. a markdown summary with best-ratio and best-throughput tables kept separate,
     so "best for archival" and "best for interactive use" are not conflated
  3. THE PLOT: compression ratio versus corpus size on a log x-axis, one line per
     backend for parmar's pipeline and its raw no-preprocessing baseline. This is
     the direct visual test of whether the ratio gap widens with scale.
  4. explicit numeric answers to the four questions in Section 7 part 4

Rows that did not round-trip verify are excluded from every comparison and reported
loudly in their own section -- a configuration that fails round-trip is itself a
finding, not something to drop quietly.
"""

import argparse
import json
import os
import sys
from collections import defaultdict

TIER_ORDER = ["64MB", "256MB", "1GB", "4GB", "8GB"]


def tier_bytes(tier):
    mult = {"MB": 1024 ** 2, "GB": 1024 ** 3}
    for suf, m in mult.items():
        if tier.upper().endswith(suf):
            return float(tier[:-2]) * m
    return 0.0


def load_rows(results):
    paths = []
    if os.path.isdir(results):
        for fn in sorted(os.listdir(results)):
            if fn.endswith(".jsonl"):
                paths.append(os.path.join(results, fn))
    else:
        paths = [results]

    rows, seen = [], {}
    for p in paths:
        with open(p, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                r["_source"] = os.path.basename(p)
                # A later row for the same cell supersedes an earlier one, so a
                # rerun-cell fix does not leave the stale failure in the analysis.
                key = (r.get("row_id"), r.get("corpus_tier"))
                seen[key] = r
    rows = list(seen.values())
    return rows


def verified(rows):
    return [r for r in rows if r.get("round_trip_verified") is True]


def fmt(x, nd=4):
    if x is None:
        return "-"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def pipeline_label(r):
    if r.get("tokenizer") == "none":
        return "raw"
    return f"{r['tokenizer']}+{r['packing']}"


# --------------------------------------------------------------------------------
# The plot (Section 7 item 3)
# --------------------------------------------------------------------------------

def make_plot(rows, out_path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed; skipping the plot (this is the harness's "
              "single most important output -- pip install matplotlib)",
              file=sys.stderr)
        return None

    # Only baseline cells, so the curve is not contaminated by OFAT perturbations.
    base = [r for r in rows if r.get("cell_kind") == "ratio_grid"]
    if not base:
        base = rows

    by_backend = defaultdict(lambda: defaultdict(dict))
    for r in base:
        by_backend[r["backend"]][pipeline_label(r)][r["corpus_tier"]] = r["ratio"]

    backends = sorted(by_backend)
    if not backends:
        return None

    ncol = 2
    nrow = (len(backends) + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(13, 3.4 * nrow), squeeze=False)
    cmap = plt.get_cmap("tab10")

    for i, backend in enumerate(backends):
        ax = axes[i // ncol][i % ncol]
        series = by_backend[backend]
        labels = sorted(series, key=lambda s: (s != "raw", s))
        for j, label in enumerate(labels):
            pts = series[label]
            tiers = [t for t in TIER_ORDER if t in pts]
            if not tiers:
                continue
            xs = [tier_bytes(t) / 1024 ** 2 for t in tiers]
            ys = [pts[t] for t in tiers]
            is_raw = label == "raw"
            ax.plot(xs, ys, marker="o" if not is_raw else "s",
                    linestyle="-" if not is_raw else "--",
                    linewidth=2.4 if is_raw else 1.7,
                    color="black" if is_raw else cmap(j % 10),
                    label=("raw bytes (baseline)" if is_raw else label),
                    zorder=5 if is_raw else 3)
        ax.set_xscale("log")
        ax.set_title(backend, fontsize=11, fontweight="bold")
        ax.set_xlabel("corpus size (MB, log scale)")
        ax.set_ylabel("compression ratio")
        ax.grid(True, alpha=0.3, which="both")
        ax.legend(fontsize=7, loc="best")

    for k in range(len(backends), nrow * ncol):
        axes[k // ncol][k % ncol].axis("off")

    fig.suptitle("parmar: compression ratio vs corpus size\n"
                 "(does the tokenized pipeline pull away from raw bytes as the "
                 "corpus outgrows the dictionary window?)",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return out_path


# Effective match window each backend can see, which is what the window-expansion
# hypothesis is actually about. zstd's is set by --long, not by the level.
WINDOW_LABEL = {
    "gzip_9": "32 KiB",
    "bz2_9": "900 KiB blk",
    "lzma_fast": "32 MiB",
    "lzma_extreme": "64 MiB",
    "lzma_tuned_lp1pb1": "64 MiB",
    "zstd_12": "128 MiB",
    "zstd_19": "128 MiB",
    "zstd_22_long": "2 GiB",
}
WINDOW_BYTES = {
    "gzip_9": 32 * 1024, "bz2_9": 900 * 1024,
    "lzma_fast": 32 * 1024 ** 2, "lzma_extreme": 64 * 1024 ** 2,
    "lzma_tuned_lp1pb1": 64 * 1024 ** 2,
    "zstd_12": 128 * 1024 ** 2, "zstd_19": 128 * 1024 ** 2,
    "zstd_22_long": 2 * 1024 ** 3,
}


def make_gap_plot(rows, out_path):
    """The hypothesis in one figure: relative ratio gap vs corpus size.

    Plotted as a percentage of the raw-backend ratio rather than in absolute ratio
    points, because absolute ratios rise with corpus size on their own -- an absolute
    gap can widen while parmar's proportional advantage shrinks.

    Two panels rather than one line per (backend, pipeline): 44 series in a single
    axes is unreadable, and the interesting comparison is across *backends* (which
    differ in window size) holding the pipeline fixed. Each panel fixes one pipeline
    and shows every backend, annotated with that backend's effective match window,
    which is the quantity the hypothesis is about.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    base = [r for r in rows if r.get("cell_kind") == "ratio_grid"] or rows
    raw = {}
    parmar = defaultdict(dict)
    for r in base:
        if r["tokenizer"] == "none":
            raw[(r["backend"], r["corpus_tier"])] = r["ratio"]
        else:
            parmar[(r["backend"], pipeline_label(r))][r["corpus_tier"]] = r["ratio"]
    for (backend, tier), val in list(raw.items()):
        if backend == "lzma_extreme" and ("lzma_tuned_lp1pb1", tier) not in raw:
            raw[("lzma_tuned_lp1pb1", tier)] = val

    panels = [
        ("p50k_base+fixed_u16", "best pipeline: p50k_base + fixed_u16"),
        ("o200k_base+leb128", "default pipeline: o200k_base + LEB128"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.5), sharey=True)
    cmap = plt.get_cmap("viridis")
    backends = sorted(WINDOW_BYTES, key=lambda b: WINDOW_BYTES[b])
    any_plotted = False

    for ax, (pipeline, title) in zip(axes, panels):
        for j, backend in enumerate(backends):
            pts = parmar.get((backend, pipeline))
            if not pts:
                continue
            tiers = [t for t in TIER_ORDER if t in pts and (backend, t) in raw]
            if len(tiers) < 2:
                continue
            xs = [tier_bytes(t) / 1024 ** 2 for t in tiers]
            ys = [(pts[t] - raw[(backend, t)]) / raw[(backend, t)] * 100
                  for t in tiers]
            ax.plot(xs, ys, marker="o", markersize=6, linewidth=2.2,
                    color=cmap(j / max(len(backends) - 1, 1)),
                    label=f"{backend}  ({WINDOW_LABEL[backend]})")
            any_plotted = True
        ax.axhline(0, color="black", linewidth=1.3, linestyle=":")
        ax.set_xscale("log")
        ax.set_xlabel("corpus size (MB, log scale)")
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.grid(True, alpha=0.3, which="both")

    if not any_plotted:
        plt.close(fig)
        return None

    axes[0].set_ylabel("ratio gap as % of the raw-backend ratio")
    handles, labels = axes[0].get_legend_handles_labels()
    if len(labels) < len(axes[1].get_legend_handles_labels()[1]):
        handles, labels = axes[1].get_legend_handles_labels()
    # One shared legend beneath the panels: an in-axes legend covers the very curves
    # the figure exists to show.
    fig.legend(handles, labels, loc="lower center", ncol=4, fontsize=9,
               title="backend (effective match window)", title_fontsize=9,
               frameon=False, bbox_to_anchor=(0.5, -0.015))
    fig.suptitle("The central question: does the parmar / raw-bytes gap widen with "
                 "corpus size?\nrising = window-expansion supported  |  flat = the "
                 "gain is representation density, not window expansion",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0.13, 1, 0.90])
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------------------
# Tables + answers
# --------------------------------------------------------------------------------

def table(rows, cols, headers=None):
    headers = headers or cols
    widths = [len(h) for h in headers]
    body = []
    for r in rows:
        cells = [str(r.get(c, "-")) for c in cols]
        body.append(cells)
        widths = [max(w, len(c)) for w, c in zip(widths, cells)]
    out = ["| " + " | ".join(h.ljust(w) for h, w in zip(headers, widths)) + " |",
           "|" + "|".join("-" * (w + 2) for w in widths) + "|"]
    for cells in body:
        out.append("| " + " | ".join(c.ljust(w) for c, w in zip(cells, widths)) + " |")
    return "\n".join(out)


def answer_q1(ok, out):
    """Does the parmar/raw-backend ratio gap grow with corpus size?"""
    out.append("### Q1. Does the parmar/raw-backend ratio gap grow with corpus size?\n")
    base = [r for r in ok if r.get("cell_kind") == "ratio_grid"] or ok
    raw = {}
    parmar = defaultdict(dict)
    for r in base:
        if r["tokenizer"] == "none":
            raw[(r["backend"], r["corpus_tier"])] = r["ratio"]
        else:
            parmar[(r["backend"], pipeline_label(r))][r["corpus_tier"]] = r["ratio"]

    # lzma_tuned_lp1pb1 has no raw counterpart by construction -- it is only valid
    # with fixed_u16 packing, so `tokenizer=none + lzma_tuned_lp1pb1` is filtered out
    # as invalid. Its honest baseline is raw bytes under lzma_extreme: the same 9e
    # preset and 64MiB dictionary, differing only in the lc/lp/pb literal context
    # that the tuning exists to change. Without this the tuned backend would silently
    # vanish from the central question's table.
    BASELINE_ALIAS = {"lzma_tuned_lp1pb1": "lzma_extreme"}
    for (backend, tier), val in list(raw.items()):
        for alias, src in BASELINE_ALIAS.items():
            if backend == src and (alias, tier) not in raw:
                raw[(alias, tier)] = val

    tiers_present = [t for t in TIER_ORDER
                     if any(t in p for p in parmar.values())]
    if not tiers_present:
        out.append("_no verified ratio-grid rows yet_\n")
        return

    lines = []
    for (backend, label), pts in sorted(parmar.items()):
        row = {"backend": backend, "pipeline": label}
        gaps = []
        for t in tiers_present:
            if t in pts and (backend, t) in raw:
                g = pts[t] - raw[(backend, t)]
                rel = g / raw[(backend, t)] * 100
                gaps.append((t, g, rel))
                row[t] = f"{g:+.4f} ({rel:+.1f}%)"
            else:
                row[t] = "-"
        if len(gaps) >= 2:
            d_abs = gaps[-1][1] - gaps[0][1]
            d_rel = gaps[-1][2] - gaps[0][2]
            row["trend"] = f"{d_abs:+.4f} ({d_rel:+.1f}pp)"
            # Judged on the relative gap: absolute ratios rise with corpus size on
            # their own, so an absolute gap can widen while parmar's proportional
            # advantage is actually shrinking. The relative change is the honest
            # test of the window-expansion claim.
            row["verdict"] = ("WIDENS" if d_rel > 0.25
                              else "NARROWS" if d_rel < -0.25
                              else "flat")
        else:
            row["trend"] = "-"
            row["verdict"] = "-"
        lines.append(row)

    out.append("Ratio gap = parmar ratio - the same backend's raw-bytes ratio, at "
               "each tier, shown absolute and as a percentage of the raw ratio. "
               "`trend` is the change from the smallest tier to the largest; the "
               "verdict is judged on the *relative* gap in percentage points, since "
               "absolute ratios rise with corpus size regardless.\n")
    out.append(table(lines, ["backend", "pipeline"] + tiers_present +
                     ["trend", "verdict"]))
    verdicts = [l["verdict"] for l in lines if l["verdict"] not in ("-",)]
    if verdicts:
        w = verdicts.count("WIDENS")
        n = verdicts.count("NARROWS")
        f = verdicts.count("flat")
        out.append(f"\n**{w} widen, {f} flat, {n} narrow** across "
                   f"{len(verdicts)} backend/pipeline combinations spanning "
                   f"{tiers_present[0]} to {tiers_present[-1]}.\n")


def answer_q2(ok, out):
    """fixed_u16 + lp1/pb1 vs LEB128 + lc3/lp0/pb0."""
    out.append("\n### Q2. Does `fixed_u16` + `lp=1,pb=1` beat `LEB128` + "
               "`lc=3,lp=0,pb=0`?\n")
    base = [r for r in ok if r.get("cell_kind") == "ratio_grid"] or ok
    idx = {}
    for r in base:
        idx[(r["corpus_tier"], r["tokenizer"], r["packing"], r["backend"])] = r["ratio"]

    lines = []
    for tier in TIER_ORDER:
        for tok in ("r50k_base", "p50k_base"):
            leb = idx.get((tier, tok, "leb128", "lzma_extreme"))
            fu_tuned = idx.get((tier, tok, "fixed_u16", "lzma_tuned_lp1pb1"))
            fu_plain = idx.get((tier, tok, "fixed_u16", "lzma_extreme"))
            if leb is None and fu_tuned is None:
                continue
            row = {
                "tier": tier, "tokenizer": tok,
                "leb128+lc3lp0pb0": fmt(leb),
                "fixed_u16+lc3lp0pb0": fmt(fu_plain),
                "fixed_u16+lc1lp1pb1": fmt(fu_tuned),
            }
            if leb and fu_tuned:
                d = (fu_tuned - leb) / leb * 100
                row["tuned vs leb128"] = f"{d:+.2f}%"
                row["verdict"] = "fixed_u16 WINS" if d > 0 else "LEB128 wins"
            else:
                row["tuned vs leb128"] = "-"
                row["verdict"] = "-"
            if fu_plain and fu_tuned:
                row["lp/pb tuning alone"] = \
                    f"{(fu_tuned - fu_plain) / fu_plain * 100:+.2f}%"
            else:
                row["lp/pb tuning alone"] = "-"
            lines.append(row)
    if not lines:
        out.append("_no verified rows for the tokenizers where both packings are "
                   "valid (r50k_base / p50k_base)_\n")
        return
    out.append(table(lines, ["tier", "tokenizer", "leb128+lc3lp0pb0",
                             "fixed_u16+lc3lp0pb0", "fixed_u16+lc1lp1pb1",
                             "tuned vs leb128", "lp/pb tuning alone", "verdict"]))


def answer_q3(ok, out):
    """manual_pool vs library_batch vs process_pool."""
    out.append("\n### Q3. Does `manual_pool` ever beat `library_batch`?\n")
    groups = defaultdict(dict)
    for r in ok:
        if r["tokenizer"] == "none" or not r.get("tokenize_time_s"):
            continue
        key = (r["corpus_tier"], r["tokenizer"], r["packing"], r["backend"],
               r["threads"], r["chunk_size"], r["batch_chunks"],
               r["backend_transport"])
        groups[key][r["tokenization_layout"]] = r

    lines = []
    for key, layouts in sorted(groups.items()):
        if "library_batch" not in layouts or len(layouts) < 2:
            continue
        lb = layouts["library_batch"]["tokenize_time_s"]
        row = {"tier": key[0], "tokenizer": key[1], "backend": key[3],
               "threads": key[4], "chunk": f"{key[5] >> 20}MB",
               "library_batch_s": fmt(lb, 2)}
        for lay in ("manual_pool", "process_pool"):
            if lay in layouts:
                t = layouts[lay]["tokenize_time_s"]
                row[lay] = f"{t:.2f} ({(lb - t) / lb * 100:+.1f}%)"
            else:
                row[lay] = "-"
        lines.append(row)
    if not lines:
        out.append("_no comparable layout groups yet_\n")
        return
    out.append("Tokenize time only (percentages are speedup vs `library_batch`; "
               "positive = faster).\n")
    out.append(table(lines, ["tier", "tokenizer", "backend", "threads", "chunk",
                             "library_batch_s", "manual_pool", "process_pool"]))

    wins = 0
    for key, layouts in groups.items():
        if "library_batch" in layouts and "manual_pool" in layouts:
            if layouts["manual_pool"]["tokenize_time_s"] < \
                    layouts["library_batch"]["tokenize_time_s"]:
                wins += 1
    comparable = sum(1 for l in groups.values()
                     if "library_batch" in l and "manual_pool" in l)
    if comparable:
        out.append(f"\n**`manual_pool` beat `library_batch` in {wins}/{comparable} "
                   f"comparable configurations.**\n")


# LZMA2 dictionary per backend; the xz block-size floor is 2x this.
LZMA_DICT = {
    "lzma_extreme": 64 * 1024 ** 2,
    "lzma_tuned_lp1pb1": 64 * 1024 ** 2,
    "lzma_fast": 32 * 1024 ** 2,
}


def compressor_input_bytes(r):
    """Bytes actually fed to the compressor, i.e. the packed stream.

    Recorded directly as `packed_bytes` on newer rows. Older rows predate that
    field, so it is reconstructed where the packing makes it exact -- raw_utf8 is
    the corpus itself and fixed_u16 is exactly two bytes per token. LEB128 is
    variable-width and cannot be reconstructed after the fact, so it returns None
    rather than a guess.
    """
    if r.get("packed_bytes"):
        return r["packed_bytes"]
    if r.get("packing") == "raw_utf8":
        return r.get("corpus_bytes")
    if r.get("packing") == "fixed_u16" and r.get("token_count"):
        return r["token_count"] * 2
    return None


def answer_q4(ok, out):
    """xz -T speedup curve and the dictionary-size floor."""
    out.append("\n### Q4. What is the real `xz -T` speedup curve, and where does the "
               "dictionary-size floor kick in?\n")
    groups = defaultdict(dict)
    for r in ok:
        if not r["backend"].startswith("lzma") or \
                r["backend_transport"] != "subprocess_cli":
            continue
        key = (r["corpus_tier"], r["tokenizer"], r["packing"], r["backend"])
        groups[key][r["threads"]] = r

    lines = []
    for key, byt in sorted(groups.items()):
        if 1 not in byt or len(byt) < 2:
            continue
        base = byt[1]
        fed = compressor_input_bytes(base)
        dict_size = LZMA_DICT.get(key[3])
        blocks = (max(1, round(fed / (2 * dict_size)))
                  if fed and dict_size else None)
        row = {"tier": key[0], "pipeline": (key[1] if key[1] != "none" else "raw"),
               "backend": key[3],
               "fed to xz": f"{fed / 1024 ** 2:.0f}MB" if fed else "?",
               "blocks": str(blocks) if blocks else "?",
               "T1_s": fmt(base["total_time_s"], 1),
               "T1_ratio": fmt(base["ratio"])}
        for th in sorted(byt):
            if th == 1:
                continue
            r2 = byt[th]
            cost = (r2["ratio"] - base["ratio"]) / base["ratio"] * 100
            row[f"T{th}"] = (f"{base['total_time_s'] / r2['total_time_s']:.2f}x "
                             f"({cost:+.2f}%)")
        lines.append(row)
    if not lines:
        out.append("_no thread-swept lzma rows yet_\n")
        return
    cols = ["tier", "pipeline", "backend", "fed to xz", "blocks", "T1_s", "T1_ratio"]
    extra = sorted({k for l in lines for k in l if k.startswith("T")
                    and k not in ("T1_s", "T1_ratio")},
                   key=lambda s: int(s[1:]))
    out.append("Speedup is wall-clock relative to `-T1`; the percentage beside it is "
               "the **ratio cost** of multithreading, since each MT block restarts "
               "with a fresh dictionary and loses cross-block redundancy.\n\n"
               "`fed to xz` is the size of the stream actually handed to the "
               "compressor -- the packed token stream, not the corpus and not the "
               "compressed output. That is the quantity that sets the block count, "
               "and it is the reason pre-tokenization has a hidden parallelism cost: "
               "shrinking the compressor's input also shrinks the number of blocks "
               "available to split across threads.\n")
    out.append(table(lines, cols + extra))
    out.append("\nThe `xz -T` block-size floor is 2x the LZMA2 dictionary -- 128MiB "
               "for the 64MiB-dict profiles, 64MiB for the 32MiB `lzma_fast` "
               "profile. `--block-size` is passed only when threads > 1, so the "
               "`-T1` rows are a clean single-block baseline with a full dictionary. "
               "Below the floor xz cannot produce more than one block, so `-T` "
               "cannot help regardless of the flag -- and correspondingly costs no "
               "ratio.\n")


def main():
    ap = argparse.ArgumentParser(description="parmar analysis (handoff Section 7)")
    ap.add_argument("--results", default="./results/")
    ap.add_argument("--out", default="./report/")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rows = load_rows(args.results)
    if not rows:
        print(f"no result rows found under {args.results}", file=sys.stderr)
        return 1
    ok = verified(rows)
    bad = [r for r in rows if r.get("round_trip_verified") is not True]

    # 1. CSV
    import csv
    keys = []
    for r in rows:
        for k in r:
            if k not in keys and not k.startswith("_"):
                keys.append(k)
    csv_path = os.path.join(args.out, "results.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # 3. plots
    plot_path = make_plot(ok, os.path.join(args.out, "ratio_vs_corpus_size.png"))
    gap_path = make_gap_plot(ok, os.path.join(args.out, "ratio_gap_vs_corpus_size.png"))

    # 2 + 4. markdown
    out = []
    out.append("# parmar sweep analysis\n")
    tiers = sorted({r["corpus_tier"] for r in ok},
                   key=lambda t: TIER_ORDER.index(t) if t in TIER_ORDER else 99)
    out.append(f"{len(rows)} result rows, **{len(ok)} round-trip verified**, "
               f"{len(bad)} not verified.  Tiers present: {', '.join(tiers) or 'none'}\n")

    if bad:
        out.append("\n## Rows excluded from all comparisons (round-trip NOT verified)\n")
        out.append("These are reported rather than dropped silently -- a "
                   "configuration that fails to round-trip is itself a finding.\n")
        out.append(table(
            [{"tier": r.get("corpus_tier"), "tokenizer": r.get("tokenizer"),
              "packing": r.get("packing"), "backend": r.get("backend"),
              "transport": r.get("backend_transport"),
              "layout": r.get("tokenization_layout"),
              "status": r.get("status"),
              "error": (str(r.get("error"))[:110] if r.get("error") else "-")}
             for r in bad],
            ["tier", "tokenizer", "packing", "backend", "transport", "layout",
             "status", "error"]))
        out.append("")

    for tier in tiers:
        sub = [r for r in ok if r["corpus_tier"] == tier]
        out.append(f"\n## Tier {tier}\n")
        out.append("### Best compression ratio (archival)\n")
        top = sorted(sub, key=lambda r: -r["ratio"])[:10]
        out.append(table(
            [{"ratio": fmt(r["ratio"]), "bytes": f"{r['compressed_bytes']:,}",
              "pipeline": pipeline_label(r), "backend": r["backend"],
              "transport": r["backend_transport"], "threads": r["threads"],
              "MB/s": fmt(r.get("throughput_mbps"), 2)} for r in top],
            ["ratio", "bytes", "pipeline", "backend", "transport", "threads", "MB/s"]))
        out.append("\n### Best throughput (interactive)\n")
        top = sorted(sub, key=lambda r: -(r.get("throughput_mbps") or 0))[:10]
        out.append(table(
            [{"MB/s": fmt(r.get("throughput_mbps"), 2), "ratio": fmt(r["ratio"]),
              "pipeline": pipeline_label(r), "backend": r["backend"],
              "transport": r["backend_transport"], "threads": r["threads"],
              "peak_rss_mb": fmt(r.get("peak_rss_mb"), 0)} for r in top],
            ["MB/s", "ratio", "pipeline", "backend", "transport", "threads",
             "peak_rss_mb"]))
        out.append("")

    out.append("\n## Section 7 part 4 -- the four questions\n")
    answer_q1(ok, out)
    answer_q2(ok, out)
    answer_q3(ok, out)
    answer_q4(ok, out)

    unsafe = [r for r in ok if r.get("unsafe_boundary_cuts")]
    if unsafe:
        out.append("\n## Chunk-boundary warnings\n")
        out.append(f"{len(unsafe)} verified rows had chunks cut at a point with no "
                   f"tokenizer-safe boundary in the lookahead window; their token "
                   f"streams depend on chunk size.\n")

    if plot_path:
        out.append(f"\n## Plots\n\n![ratio vs corpus size]({os.path.basename(plot_path)})\n")
    if gap_path:
        out.append(f"\n![ratio gap]({os.path.basename(gap_path)})\n")

    md_path = os.path.join(args.out, "summary.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")

    print(f"wrote {csv_path}")
    print(f"wrote {md_path}")
    if plot_path:
        print(f"wrote {plot_path}")
    if gap_path:
        print(f"wrote {gap_path}")
    print(f"\n{len(ok)}/{len(rows)} rows round-trip verified across tiers: "
          f"{', '.join(tiers)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
