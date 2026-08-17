#!/usr/bin/env python3
"""Figures for the parmar sweep. Imported by analyze.py.

Each figure is rendered twice -- once for a light surface, once for a dark one --
because GitHub serves READMEs in both themes and an automatic flip of a light
chart is not a dark chart. The dark palette is the same hues re-stepped for the
dark surface, not an inversion.

The categorical palette and its slot ORDER are load-bearing, not cosmetic: the
order is what keeps adjacent series separable under colour-vision deficiency.
Both sets were checked with a validator rather than eyeballed:

  4 slots, adjacent pairs (line charts)
      light  worst CVD dE 9.1, normal-vision 22.9   PASS
      dark   worst CVD dE 8.4, normal-vision 19.8   PASS
  3 slots, ALL pairs (scatter -- every pair is adjacent when points interleave)
      light  worst CVD dE 9.2, normal-vision 24.0   PASS
      dark   worst CVD dE 9.4, normal-vision 20.9   PASS

Scatter plots are therefore capped at three categorical colours; line charts may
use four. Where more classes exist than the cap allows they are grouped, or the
second dimension moves to line style / marker shape rather than to a fifth hue.

Corpus size is a magnitude, so where tiers are encoded by colour they use a
single-hue ordinal ramp, never categorical hues.
"""

from collections import defaultdict

TIER_ORDER = ["64MB", "256MB", "1GB", "4GB", "8GB"]

THEME = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "ink2": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        # categorical slots 1-4, in validated order
        "cat": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"],
        # blue ordinal ramp, light surface: start no lighter than step 250
        "ramp": ["#86b6ef", "#3987e5", "#2a78d6", "#1c5cab", "#0d366b"],
        "ref": "#52514e",
    },
    "dark": {
        "surface": "#1a1a19",
        "ink": "#ffffff",
        "ink2": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "cat": ["#3987e5", "#d95926", "#199e70", "#c98500"],
        # blue ordinal ramp, dark surface: go no darker than step 600
        "ramp": ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#184f95"],
        "ref": "#c3c2b7",
    },
}

# Backend -> (family, variant). Family drives colour (4 categorical slots),
# variant drives line style, so eight backends never need eight hues.
FAMILY = {
    "lzma_extreme": ("lzma", "9e  lc3 lp0 pb0"),
    "lzma_fast": ("lzma", "preset 6"),
    "lzma_tuned_lp1pb1": ("lzma", "9e  lc1 lp1 pb1"),
    "zstd_19": ("zstd", "-19"),
    "zstd_12": ("zstd", "-12"),
    "zstd_22_long": ("zstd", "-22 --long=31"),
    "gzip_9": ("gzip", "-9"),
    "bz2_9": ("bzip2", "-9"),
}
FAMILY_ORDER = ["lzma", "zstd", "gzip", "bzip2"]
STYLE = ["-", "--", ":"]

WINDOW_LABEL = {
    "gzip_9": "32 KiB", "bz2_9": "900 KiB blk",
    "lzma_fast": "32 MiB", "lzma_extreme": "64 MiB",
    "lzma_tuned_lp1pb1": "64 MiB",
    "zstd_12": "128 MiB", "zstd_19": "128 MiB", "zstd_22_long": "2 GiB",
}
LZMA_DICT = {"lzma_extreme": 64 << 20, "lzma_tuned_lp1pb1": 64 << 20,
             "lzma_fast": 32 << 20}


def tier_mb(t):
    mult = {"MB": 1, "GB": 1024}
    for suf, m in mult.items():
        if t.upper().endswith(suf):
            return float(t[:-2]) * m
    return 0.0


def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _style_axes(ax, th, xlabel=None, ylabel=None, title=None, logx=False):
    """Hairline recessive chrome; solid gridlines (dashed grid reads as a threshold)."""
    ax.set_facecolor(th["surface"])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(th["axis"])
        ax.spines[side].set_linewidth(0.8)
    ax.grid(True, which="major", color=th["grid"], linewidth=0.7, linestyle="-")
    ax.set_axisbelow(True)
    ax.tick_params(colors=th["muted"], labelsize=8.5, length=3, width=0.8)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color(th["muted"])
    if logx:
        ax.set_xscale("log")
    if xlabel:
        ax.set_xlabel(xlabel, color=th["ink2"], fontsize=9)
    if ylabel:
        ax.set_ylabel(ylabel, color=th["ink2"], fontsize=9)
    if title:
        ax.set_title(title, color=th["ink"], fontsize=10.5, fontweight="bold",
                     pad=8)


def _finish(fig, th, path, suptitle=None, sub=None):
    fig.patch.set_facecolor(th["surface"])
    if suptitle:
        y = 0.985
        fig.suptitle(suptitle, color=th["ink"], fontsize=13, fontweight="bold",
                     y=y)
        if sub:
            fig.text(0.5, y - 0.045, sub, ha="center", color=th["ink2"],
                     fontsize=9.5)
    fig.savefig(path, dpi=150, facecolor=th["surface"])
    _mpl().close(fig)
    return path


def _legend(fig, handles, labels, th, ncol=4, y=0.0, title=None):
    """One shared legend below the panels; identity is never colour-alone."""
    leg = fig.legend(handles, labels, loc="lower center", ncol=ncol, fontsize=8.5,
                     frameon=False, bbox_to_anchor=(0.5, y), title=title)
    if title:
        leg.get_title().set_color(th["ink2"])
        leg.get_title().set_fontsize(8.5)
    for t in leg.get_texts():
        t.set_color(th["ink2"])          # text wears ink, not the series colour
    return leg


# --------------------------------------------------------------------------------
# helpers over the result rows
# --------------------------------------------------------------------------------

def _grid(rows):
    return [r for r in rows if r.get("cell_kind") == "ratio_grid"] or rows


def _pipeline(r):
    return "raw" if r["tokenizer"] == "none" else f"{r['tokenizer']}+{r['packing']}"


def _raw_and_parmar(rows):
    raw, pm = {}, defaultdict(dict)
    for r in _grid(rows):
        if r["tokenizer"] == "none":
            raw[(r["backend"], r["corpus_tier"])] = r["ratio"]
        else:
            pm[(r["backend"], _pipeline(r))][r["corpus_tier"]] = r["ratio"]
    # lzma_tuned_lp1pb1 has no raw counterpart by construction (it is only valid
    # with fixed_u16); its honest baseline is raw under lzma_extreme -- same 9e
    # preset and 64MiB dictionary, differing only in the lc/lp/pb it exists to change.
    for (b, t), v in list(raw.items()):
        if b == "lzma_extreme":
            raw.setdefault(("lzma_tuned_lp1pb1", t), v)
    return raw, pm


# --------------------------------------------------------------------------------
# Figure 1 -- the central question
# --------------------------------------------------------------------------------

def fig_gap(rows, path, mode):
    """Relative ratio gap vs corpus size, two pipelines, all backends.

    Plotted as a percentage of the raw-backend ratio, not in absolute ratio
    points: absolute ratios rise with corpus size on their own, so an absolute
    gap can widen while the proportional advantage shrinks.
    """
    plt = _mpl()
    th = THEME[mode]
    raw, pm = _raw_and_parmar(rows)
    panels = [("p50k_base+fixed_u16", "best pipeline:  p50k_base + fixed_u16"),
              ("o200k_base+leb128", "default pipeline:  o200k_base + LEB128")]

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 6.2), sharey=True)
    seen = {}
    for ax, (pipe, title) in zip(axes, panels):
        drawn = []
        for backend in sorted(FAMILY, key=lambda b: (
                FAMILY_ORDER.index(FAMILY[b][0]), b)):
            pts = pm.get((backend, pipe))
            if not pts:
                continue
            tiers = [t for t in TIER_ORDER if t in pts and (backend, t) in raw]
            if len(tiers) < 2:
                continue
            fam, variant = FAMILY[backend]
            colour = th["cat"][FAMILY_ORDER.index(fam)]
            ls = STYLE[sorted(b for b in FAMILY if FAMILY[b][0] == fam)
                       .index(backend) % len(STYLE)]
            xs = [tier_mb(t) for t in tiers]
            ys = [(pts[t] - raw[(backend, t)]) / raw[(backend, t)] * 100
                  for t in tiers]
            line, = ax.plot(xs, ys, ls, color=colour, linewidth=2.0,
                            marker="o", markersize=5.5,
                            markeredgecolor=th["surface"], markeredgewidth=1.2,
                            zorder=3)
            seen.setdefault(f"{backend}  ({WINDOW_LABEL[backend]})", line)
            drawn.append((backend, xs, ys, colour))

        # Direct-label selectively -- the extremes and the steepest riser, not all
        # eight endpoints. Eight labels at these values collide, and a number on
        # every series is unreadable anyway; the legend and the tables carry the rest.
        if drawn:
            hi = max(drawn, key=lambda d: d[2][-1])
            lo = min(drawn, key=lambda d: d[2][-1])
            climb = max(drawn, key=lambda d: d[2][-1] - d[2][0])
            for backend, xs, ys, colour in {id(d): d for d in (hi, lo, climb)}.values():
                note = f"{ys[-1]:+.1f}%"
                if backend == climb[0] and climb is not hi and climb is not lo:
                    note += f"  (from {ys[0]:+.1f}%)"
                ax.annotate(note, (xs[-1], ys[-1]), textcoords="offset points",
                            xytext=(9, -3), fontsize=8.5, color=th["ink2"],
                            fontweight="bold", zorder=5)
        ax.axhline(0, color=th["ref"], linewidth=1.1, zorder=2)
        _style_axes(ax, th, "corpus size (MB, log scale)", None, title, logx=True)
        ax.set_xlim(45, 9000)
    axes[0].set_ylabel("ratio gap, % of the raw-backend ratio", color=th["ink2"],
                       fontsize=9)

    order = sorted(seen, key=lambda l: (
        FAMILY_ORDER.index(FAMILY[l.split()[0]][0]), l))
    _legend(fig, [seen[l] for l in order], order, th, ncol=4, y=-0.005,
            title="backend  (effective match window)   ·   colour = family, "
                  "line style = variant")
    fig.tight_layout(rect=[0, 0.13, 1, 0.88])
    return _finish(fig, th, path,
                   "Does the parmar / raw-bytes gap widen with corpus size?",
                   "rising = window expansion  ·  flat = the gain is representation "
                   "density  ·  below zero = pre-tokenizing hurts")


# --------------------------------------------------------------------------------
# Figure 2 -- absolute ratio, small multiples per backend
# --------------------------------------------------------------------------------

def fig_ratio_small_multiples(rows, path, mode):
    plt = _mpl()
    th = THEME[mode]
    raw, pm = _raw_and_parmar(rows)
    # Small multiples are an all-pairs form, so two categorical series only; raw
    # is the reference and wears ink rather than a categorical hue.
    series = [("o200k_base+leb128", th["cat"][0], "-"),
              ("p50k_base+fixed_u16", th["cat"][1], "-")]

    backends = [b for b in sorted(FAMILY, key=lambda b: (
        FAMILY_ORDER.index(FAMILY[b][0]), b))
        if any((b, s) in pm for s, _, _ in series)]
    ncol, nrow = 4, (len(backends) + 3) // 4
    fig, axes = plt.subplots(nrow, ncol, figsize=(15, 3.5 * nrow),
                             squeeze=False, sharex=True)
    handles, labels = [], []
    for i, backend in enumerate(backends):
        ax = axes[i // ncol][i % ncol]
        tiers = [t for t in TIER_ORDER if (backend, t) in raw]
        if tiers:
            l0, = ax.plot([tier_mb(t) for t in tiers],
                          [raw[(backend, t)] for t in tiers], "-",
                          color=th["ref"], linewidth=2.4, marker="s",
                          markersize=5, markeredgecolor=th["surface"],
                          markeredgewidth=1.2, zorder=4)
            if not labels:
                handles.append(l0); labels.append("raw bytes (no pre-filter)")
        for name, colour, ls in series:
            pts = pm.get((backend, name))
            if not pts:
                continue
            tt = [t for t in TIER_ORDER if t in pts]
            ln, = ax.plot([tier_mb(t) for t in tt], [pts[t] for t in tt], ls,
                          color=colour, linewidth=2.0, marker="o",
                          markersize=5.5, markeredgecolor=th["surface"],
                          markeredgewidth=1.2, zorder=3)
            if name not in labels:
                handles.append(ln); labels.append(name)
        _style_axes(ax, th, "corpus size (MB, log)" if i // ncol == nrow - 1 else None,
                    "compression ratio" if i % ncol == 0 else None,
                    f"{backend}   ({WINDOW_LABEL[backend]})", logx=True)
    for k in range(len(backends), nrow * ncol):
        axes[k // ncol][k % ncol].axis("off")

    _legend(fig, handles, labels, th, ncol=3, y=0.005)
    fig.tight_layout(rect=[0, 0.07, 1, 0.90])
    return _finish(fig, th, path,
                   "Compression ratio vs corpus size, per backend",
                   "higher is better  ·  the tokenized lines pull away from raw "
                   "bytes only where the backend has a window to expand")


# --------------------------------------------------------------------------------
# Figure 3 -- ratio / throughput trade-off with the Pareto frontier
# --------------------------------------------------------------------------------

def fig_pareto(rows, path, mode, tier="1GB"):
    plt = _mpl()
    th = THEME[mode]
    pts = [r for r in _grid(rows) if r["corpus_tier"] == tier
           and r.get("throughput_mbps") and r.get("ratio")]
    if not pts:
        return None
    # Scatter is an all-pairs form: three categorical colours maximum, so the
    # eight backends group into three families rather than getting eight hues.
    def group(r):
        fam = FAMILY[r["backend"]][0]
        return fam if fam in ("lzma", "zstd") else "gzip / bzip2"
    groups = ["lzma", "zstd", "gzip / bzip2"]

    fig, ax = plt.subplots(figsize=(11, 7))
    for gi, g in enumerate(groups):
        sub = [r for r in pts if group(r) == g]
        if not sub:
            continue
        ax.scatter([r["throughput_mbps"] for r in sub], [r["ratio"] for r in sub],
                   s=58, color=th["cat"][gi], label=g, zorder=3,
                   edgecolor=th["surface"], linewidth=1.4, alpha=0.95)

    # Pareto frontier: nothing is both faster and smaller than these.
    front = []
    for r in sorted(pts, key=lambda r: -r["ratio"]):
        if not front or r["throughput_mbps"] > front[-1]["throughput_mbps"]:
            front.append(r)
    ax.step([r["throughput_mbps"] for r in front], [r["ratio"] for r in front],
            where="post", color=th["ref"], linewidth=1.4, linestyle="-",
            zorder=2, label="Pareto frontier")
    # Frontier points carry a numeral and are named in a keyed list instead of an
    # inline label each. Inline labels here overlap into illegibility -- the
    # frontier's whole point is that its members are close together -- and a
    # collision-avoidance nudge in data units cannot be reasoned about reliably
    # against a log axis. The numerals never collide.
    key = []
    for i, r in enumerate(front, 1):
        ax.annotate(str(i), (r["throughput_mbps"], r["ratio"]),
                    textcoords="offset points", xytext=(0, 0), ha="center",
                    va="center", fontsize=7.5, fontweight="bold",
                    color=th["surface"], zorder=6)
        key.append(f"{i}.  {r['ratio']:.3f}x  ·  {r['throughput_mbps']:>5.1f} MB/s"
                   f"   {_pipeline(r)} · {r['backend']}")
    ax.text(0.015, 0.03, "Pareto frontier — nothing is both smaller and faster\n"
            + "\n".join(key), transform=ax.transAxes, fontsize=7.8,
            color=th["ink2"], va="bottom", ha="left", linespacing=1.6,
            family="monospace", zorder=6)

    _style_axes(ax, th, "compression throughput (MB/s of original text, log scale)",
                "compression ratio", None, logx=True)
    h, l = ax.get_legend_handles_labels()
    _legend(fig, h, l, th, ncol=4, y=0.005, title=f"backend family  ·  {tier} tier")
    fig.tight_layout(rect=[0, 0.08, 1, 0.89])
    return _finish(fig, th, path,
                   "Ratio vs speed: what you would actually pick",
                   f"{tier} tier, all verified configurations. Up and to the right "
                   f"is better; the frontier is the set nothing dominates.")


# --------------------------------------------------------------------------------
# Figure 4 -- the xz -T law, and the multithreading ratio cost
# --------------------------------------------------------------------------------

def _packed(r):
    if r.get("packed_bytes"):
        return r["packed_bytes"]
    if r.get("packing") == "raw_utf8":
        return r.get("corpus_bytes")
    if r.get("packing") == "fixed_u16" and r.get("token_count"):
        return r["token_count"] * 2
    return None


def fig_threads(rows, path, mode, cores=20):
    plt = _mpl()
    th = THEME[mode]
    byconf = defaultdict(dict)
    for r in rows:
        if r.get("backend_transport") == "subprocess_cli":
            byconf[(r["corpus_tier"], _pipeline(r), r["backend"])][r["threads"]] = r

    pts, percell = [], defaultdict(list)
    for (tier, pipe, backend), byt in byconf.items():
        if 1 not in byt:
            continue
        base = byt[1]
        for th_n, r in byt.items():
            if th_n == 1:
                continue
            percell[backend].append(
                (r["ratio"] - base["ratio"]) / base["ratio"] * 100)
        if backend not in LZMA_DICT:
            continue
        fed = _packed(base)
        if not fed:
            continue
        blocks = max(1, round(fed / (2 * LZMA_DICT[backend])))
        for th_n in (4, cores):
            if th_n in byt:
                pts.append((blocks, base["total_time_s"] / byt[th_n]["total_time_s"],
                            th_n, tier))

    fig, axes = plt.subplots(1, 2, figsize=(14, 6.2),
                             gridspec_kw={"width_ratios": [1.35, 1]})

    ax = axes[0]
    lim = max([p[0] for p in pts] + [cores]) * 1.35 if pts else 70
    ax.plot([1, lim], [1, lim], "-", color=th["axis"], linewidth=1.2, zorder=1)
    ax.annotate("speedup = block count", (lim * 0.30, lim * 0.30),
                rotation=32, fontsize=8, color=th["muted"], zorder=1)
    ax.axhline(cores, color=th["ref"], linewidth=1.1, zorder=1)
    ax.annotate(f"{cores} cores — hardware ceiling", (1.15, cores * 1.06),
                fontsize=8, color=th["ink2"], zorder=4)
    # threads is ordered, so it uses a single-hue ordinal ramp, not two hues
    for i, th_n in enumerate(sorted({p[2] for p in pts})):
        sub = [p for p in pts if p[2] == th_n]
        ax.scatter([p[0] for p in sub], [p[1] for p in sub], s=62,
                   color=th["ramp"][1 + i * 2], label=f"-T{th_n}", zorder=3,
                   edgecolor=th["surface"], linewidth=1.4)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(0.8, lim); ax.set_ylim(0.8, lim)
    _style_axes(ax, th, "blocks available  =  bytes fed to xz / (2 x dictionary)",
                "wall-clock speedup vs -T1",
                "Speedup is set by the block count, then by cores")
    h1, l1 = ax.get_legend_handles_labels()
    leg = ax.legend(h1, l1, fontsize=8.5, frameon=False, loc="upper left")
    for t in leg.get_texts():
        t.set_color(th["ink2"])

    # Per-backend strip plot rather than bars: zstd's cost is exactly 0.00%, and a
    # zero-height bar is invisible -- the reader would see an empty slot and not
    # know whether it means "zero" or "no data". Dots put the zero on the line.
    ax = axes[1]
    rowlbl, rows_ = [], []
    for backend in sorted(percell, key=lambda b: (
            FAMILY_ORDER.index(FAMILY[b][0]), b)):
        rowlbl.append(backend)
        rows_.append(percell[backend])
    ax.axvline(0, color=th["ref"], linewidth=1.1, zorder=2)
    for i, (backend, vals) in enumerate(zip(rowlbl, rows_)):
        colour = th["cat"][FAMILY_ORDER.index(FAMILY[backend][0])]
        ax.scatter(vals, [i] * len(vals), s=46, color=colour, zorder=3,
                   edgecolor=th["surface"], linewidth=1.3, alpha=0.95)
        m = sum(vals) / len(vals)
        ax.annotate(f"{m:+.2f}%", (m, i), textcoords="offset points",
                    xytext=(0, 11), ha="center", fontsize=8.5,
                    fontweight="bold", color=th["ink2"], zorder=4)
    ax.set_yticks(range(len(rowlbl)))
    ax.set_yticklabels(rowlbl, fontsize=8.5)
    ax.set_ylim(-0.7, len(rowlbl) - 0.3)
    _style_axes(ax, th, "ratio change from multithreading (%)", None,
                "What multithreading costs in ratio")
    ax.grid(axis="y", visible=False)
    ax.annotate("gzip and bzip2 have no -T option at all,\nso they cannot appear here",
                (0.5, -0.62), xycoords=("axes fraction", "data"), ha="center",
                fontsize=7.5, color=th["muted"], zorder=4)

    fig.tight_layout(rect=[0, 0.02, 1, 0.88])
    return _finish(fig, th, path,
                   "Multithreading: what it buys, and what it costs",
                   "left: below one block, -T cannot help at all; above it, "
                   "speedup tracks blocks until cores run out.  "
                   "right: xz restarts the dictionary per block, zstd does not.")


# --------------------------------------------------------------------------------
# Figure 5 -- where the fixed_u16 win actually comes from
# --------------------------------------------------------------------------------

def fig_packing_waterfall(rows, path, mode, tier="1GB"):
    """Decomposition, so a waterfall rather than a bar chart of three numbers."""
    plt = _mpl()
    th = THEME[mode]
    idx = {}
    for r in _grid(rows):
        idx[(r["corpus_tier"], r["tokenizer"], r["packing"], r["backend"])] = r["ratio"]

    toks = [t for t in ("r50k_base", "p50k_base")
            if (tier, t, "leb128", "lzma_extreme") in idx]
    if not toks:
        return None

    fig, axes = plt.subplots(1, len(toks), figsize=(6.4 * len(toks), 6.0),
                             sharey=True, squeeze=False)
    for ax, tok in zip(axes[0], toks):
        leb = idx[(tier, tok, "leb128", "lzma_extreme")]
        fu = idx[(tier, tok, "fixed_u16", "lzma_extreme")]
        tuned = idx.get((tier, tok, "fixed_u16", "lzma_tuned_lp1pb1"), fu)
        steps = [("LEB128\nlc3 lp0 pb0", leb, 0.0, th["cat"][0]),
                 ("+ fixed_u16\n(fixed 2-byte width)", fu, fu - leb, th["cat"][1]),
                 ("+ lc1 lp1 pb1\n(alignment tuning)", tuned, tuned - fu,
                  th["cat"][2])]
        base = min(leb, fu, tuned) - 0.06
        for i, (lbl, top, delta, colour) in enumerate(steps):
            bottom = base if i == 0 else steps[i - 1][1]
            ax.bar(i, top - bottom, bottom=bottom, width=0.56, color=colour,
                   edgecolor=th["surface"], linewidth=1.8, zorder=3)
            if i:
                ax.plot([i - 1 + 0.28, i - 0.28], [bottom, bottom], "-",
                        color=th["axis"], linewidth=1.0, zorder=2)
            ax.annotate(f"{top:.4f}x", (i, top), textcoords="offset points",
                        xytext=(0, 6), ha="center", fontsize=9.5,
                        fontweight="bold", color=th["ink"], zorder=4)
            if i:
                ax.annotate(f"{delta / bottom * 100:+.2f}%",
                            (i, bottom + (top - bottom) / 2),
                            textcoords="offset points", xytext=(0, 0),
                            ha="center", va="center", fontsize=9,
                            color=th["surface"], fontweight="bold", zorder=5)
        ax.set_xticks(range(3))
        ax.set_xticklabels([s[0] for s in steps], fontsize=8.5)
        _style_axes(ax, th, None,
                    "compression ratio" if tok == toks[0] else None,
                    f"{tok}   ({tier} tier, lzma 9e)")
        ax.set_ylim(base, max(leb, fu, tuned) + 0.10)
        ax.grid(axis="x", visible=False)

    fig.tight_layout(rect=[0, 0.01, 1, 0.86])
    return _finish(fig, th, path,
                   "Where the fixed-width win actually comes from",
                   "the alignment tuning the theory argued for is real but small; "
                   "most of the gain is the fixed 2-byte period itself")


# --------------------------------------------------------------------------------

FIGURES = [
    ("ratio_gap_vs_corpus_size", fig_gap),
    ("ratio_vs_corpus_size", fig_ratio_small_multiples),
    ("ratio_vs_throughput_pareto", fig_pareto),
    ("thread_scaling", fig_threads),
    ("packing_decomposition", fig_packing_waterfall),
]


def render_all(rows, out_dir, verbose=True):
    import os
    made = []
    for stem, fn in FIGURES:
        for mode in ("light", "dark"):
            suffix = "" if mode == "light" else "_dark"
            path = os.path.join(out_dir, f"{stem}{suffix}.png")
            try:
                got = fn(rows, path, mode)
            except Exception as exc:
                print(f"  ! {stem} ({mode}) failed: {type(exc).__name__}: {exc}")
                continue
            if got:
                made.append(got)
                if verbose:
                    print(f"  wrote {got}")
    return made
