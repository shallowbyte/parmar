# Contributing to parmar

This is a research harness, not a product. Its output is only worth anything if the
numbers are trustworthy, so the contribution rules are mostly about that.

## The three rules that matter

**1. Round-trip verification is non-negotiable.**

No ratio, throughput, or size number goes into a results file unless that
configuration's decompression was actually executed and its sha256 actually matched
the archive footer. If you add a packing scheme, backend, transport, or tokenization
layout, it gets the same treatment *before* it is trusted, not after. `run_cell.py`
enforces this: a cell that fails round-trip still reports its ratio, but reports
`round_trip_verified: false` alongside it, and `analyze.py` excludes it from every
comparison and lists it loudly.

**2. Silent fallbacks are bugs.**

If a tool is missing, a threshold is not met, or a configuration is invalid: print
why, and skip. Do not quietly degrade to something else. This project has been bitten
by exactly this three separate times:

* multithreaded LZMA silently falling back to single-threaded when `xz` was absent
* the same, when `xz` was present but the payload was under the block-size floor
* `lzma_fast` meaning `MODE_FAST/MF_HC4/nice_len=32` in-process but `preset=6` via
  the CLI -- a 21% size difference that would have made the transport axis measure
  the wrong thing entirely

**3. Correctness before scale; small before big.**

Do not run a new code path against a 1GB+ tier before it has round-tripped at 64MB.
A bug that takes 20 seconds to reproduce at 64MB takes 20+ minutes at 4GB with
`preset=9e`. Cheap iteration loops are a correctness tool here, not a convenience.

## Before opening a PR

```bash
python parmar.py selftest                    # packing property/fuzz test
python test_regressions.py                   # the defects found in the prototype
python test_axes.py --slice-mb 8             # every axis value round-trips
python matrix.py verify-boundaries --corpus ./corpus/pg19_64mb.txt \
    --tokenizers "o200k_base,cl100k_base,r50k_base,p50k_base" \
    --chunk-sizes "1MB,2MB,4MB"              # BLOCKING -- must pass
python matrix.py smoke --corpus ./corpus/pg19_64mb.txt
```

`verify-boundaries` is the one that will catch you. It asserts that splitting the
input at chunk boundaries produces a byte-identical token sequence to tokenizing the
whole stream. If you touch `read_chunks`, `find_safe_boundary`, or
`trim_to_utf8_boundary`, it must still pass for **every** tokenizer -- the
pretokenization regexes differ between the o200k/cl100k family and the GPT-2 family,
and a rule that is safe for one is not automatically safe for the other. See
`FINDINGS.md` §4 for the failure this test already caught.

## If you change a backend definition

Existing result rows for that backend become stale, and resume will skip them
forever. Drop them first:

```bash
python prune_results.py results/sweep_64mb.jsonl \
    --backend-prefix lzma --transport in_process_binding --dry-run
```

## Adding a matrix axis value

1. Add it to the relevant table in `parmar_core.py` (`BACKENDS`, `PACKING_CODES`,
   `TOKENIZATION_LAYOUTS`, `TRANSPORTS`).
2. Add a validity rule to `validity_drop_reason` in `matrix.py` if some combinations
   are meaningless, and an availability rule to `availability_drop_reason` if it
   depends on an external tool or optional package. Every dropped cell must carry a
   human-readable reason -- the drop log is evidence the filter works.
3. Add it to `test_axes.py` and confirm it round-trips at 8MB.
4. Only then let it into a sweep.

## Code style

Match the surrounding code. It is deliberately comment-light: comments are reserved
for *judgment calls and non-obvious constraints*, not for narrating what the code
does. If you make a call the handoff spec does not answer, document it inline at the
definition and say why -- that is exactly what comments are for here.

## Reporting a negative result

A clean negative is a useful outcome, not a failure. If a hypothesis in the README
does not hold up under your measurement, say so plainly with the numbers. The
harness is built to show either outcome honestly; please keep it that way.
