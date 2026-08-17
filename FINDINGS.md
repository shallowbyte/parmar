# Findings: what turned out to be wrong once the code could actually be run

`parmar.py` and `PARMAR_HANDOFF.md` were written under a no-execution constraint.
This file records everything that only became visible once the code was executed.
None of it is a criticism of the earlier work -- it is the expected yield of
removing that constraint, and the design spec explicitly asked for it.

---

## 1. The dataset instruction cannot be followed as written

The design spec specifies:

```python
datasets.load_dataset("deepmind/pg19", split="train", streaming=True)
```

Querying the Hub API shows this cannot work:

* `deepmind/pg19` contains exactly six files: `.gitattributes`, `README.md`,
  `pg19.py`, and `data/{train,validation,test}_files.txt`. **There is no parquet and
  no arrow data in the repo.**
* Its `refs/convert/parquet` branch contains only `README.md`,
  `dataset_infos.json` and a copy of the script -- the Hub's automatic parquet
  conversion never produced data for this dataset, so the usual script-free fallback
  does not exist either.
* `pg19.py` is a `GeneratorBasedBuilder` that downloads each book from
  `https://storage.googleapis.com/deepmind-gutenberg/`. **Loading scripts were
  removed outright in `datasets` 3.0**, so this path additionally requires pinning a
  deprecated major version and passing `trust_remote_code=True`.

**Resolution:** `build_corpus.py` reads the authoritative file list from the repo and
fetches the books directly from GCS with a bounded, order-preserving thread pool.
Every requirement of the design spec is kept (document-boundary accumulation, per-tier
checkpoints, recorded sha256/doc-count/byte-count, fixed-seed shuffle) and the
`datasets` dependency is dropped entirely.

Measured: 0.93 MB/s single-connection, 3.46 MB/s at 64 workers.

---

## 2. `read_chunks` could cut mid-UTF-8-codepoint  (`parmar.py:190-220`)

`safe_utf8_boundary(data, end)` began with:

```python
if end >= n:
    return n
```

and its only call site was:

```python
end = probe + 1 if probe < limit else safe_utf8_boundary(probe_buf, limit)
```

where `limit == len(probe_buf)`. So on the branch that needed the backoff -- no
delimiter found anywhere in the lookahead window -- the guard fired immediately and
the function was a **no-op**. The chunk was then cut at whatever byte the 4096-byte
lookahead read happened to end on.

**Reproduced**, not merely reasoned about: a file with ~2MB of delimited text
followed by a delimiter-free run of 2-byte codepoints raised

```
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xc3 in position 2101247:
unexpected end of data
```

from `encode_and_feed`'s `chunk.decode("utf-8", errors="strict")`.

**Resolution:** `trim_to_utf8_boundary` scans backwards from the tail, so it works
when the cut point *is* the end of the buffer. Regression test in
`test_regressions.py` covers 2-, 3- and 4-byte codepoints at every partial offset.

---

## 3. Decompression corrupted characters split across token batches  (`parmar.py:495`)

Decompression reassembled ~500k-token batches with:

```python
text = enc.decode(ids_list)
encoded = text.encode("utf-8")
```

tiktoken's `Encoding.decode` defaults to `errors="replace"`, and its tokens are
byte-level, so a multi-byte character whose UTF-8 bytes span two tokens is silently
replaced with U+FFFD when the batch boundary falls between them.

**Reproduced:** `'\U0001F926\U0001F3FC‍♂️'` tokenizes to
`[50378, 99, 183024, 2524, 178729, 15148]` under `o200k_base`. Splitting after the
first token gives

```
original            b'\xf0\x9f\xa4\xa6\xf0\x9f\x8f\xbc...'
decode()   path     b'\xef\xbf\xbd\xef\xbf\xbd\xf0\x9f\x8f\xbc...'   <- two U+FFFD
decode_bytes() path b'\xf0\x9f\xa4\xa6\xf0\x9f\x8f\xbc...'           <- exact
```

The sha256 check would have caught this, so it would have surfaced as a mysterious
round-trip failure on some corpora rather than as silent corruption -- but it would
have been attributed to the wrong component.

**Resolution:** `enc.decode_bytes(ids)` everywhere, which returns raw bytes and
concatenates correctly at any split point (and is faster, since it skips a decode
and re-encode round trip).

---

## 4. THE BIG ONE: chunk-boundary splitting was NOT token-safe

The design spec asserts, in three places, that cutting at whitespace/punctuation
delimiters "produces token-identical output to tokenizing the whole stream at once",
and the design spec flags that this was never actually verified. It is **false** as
implemented.

`parmar.py` cut *after* a delimiter (`end = probe + 1`) using
`DELIMS = frozenset(b" \t\n\r.,;:!?\"')]}")`. Every tiktoken pretokenizer attaches
whitespace as a **leading** prefix to the word that follows it -- ` ?\p{L}+` in the
GPT-2 family, `[^\r\n\p{L}\p{N}]?[letters]+` in o200k/cl100k. Cutting after the
space therefore orphaned the space from its word.

**Measured on the 64MB PG-19 corpus with `o200k_base`:**

| | tokens |
|---|---|
| unsplit | 16,020,945 |
| split at 1MB chunks | 16,020,999 |

First divergence at token index 251,996, byte offset 1,048,580, chunk boundary at
1,048,581:

```
unsplit  [... 2023,  1983, 842, 117715, ...]      1983  = " and"
split    [... 2023,  220, 5037, 842, 117715, ...] 220   = " ",  5037 = "and"
```

This is precisely the failure mode the design spec predicted -- *"the regex pretoken
pattern's leading-optional-non-letter-character behavior pulling a byte across what
looks like a clean split"* -- and it affected **all four tokenizers**, not just
`o200k_base`.

The magnitude is small (~1 extra token per boundary, ~0.0003% of the stream), so it
would never have been noticed as a ratio anomaly. But it means the token stream is a
function of chunk size, which would have put tokenizer-specific noise into the
`chunk_size` axis of the matrix and made that axis uninterpretable.

**Resolution:** cut so the chunk ends on an ASCII alphanumeric and the whitespace run
travels with the *following* chunk (`find_safe_boundary` in `parmar_core.py`). This is
safe for both pretokenizer families:

* the preceding chunk ends inside a word or number pretoken, which has no trailing
  optional element that could reach across the boundary
* the following chunk starts at a whitespace run, which is where every
  whitespace-absorbing alternative in both regexes starts anyway
* ending on a non-whitespace character also avoids the GPT-2 family's end-of-string
  `\s+(?!\S)` alternative regrouping a trailing `\r\n` that the joined text would
  have split -- which matters because PG-19 uses CRLF line endings
* both bytes are ASCII, so the cut is a valid UTF-8 boundary for free

`MAX_LOOKAHEAD` was raised from 4096 to 65536 because the new rule is stricter.

**Verification** (`verify_boundaries.py`, 64MB corpus):

| tokenizer | 1MB | 2MB | 4MB | unsafe cuts |
|---|---|---|---|---|
| `o200k_base`  | identical | identical | identical | 0 |
| `cl100k_base` | identical | identical | identical | 0 |
| `r50k_base`   | identical | identical | identical | 0 |
| `p50k_base`   | identical | identical | identical | 0 |

**Known limitation, reported not hidden:** the rule needs an ASCII alphanumeric
followed by whitespace somewhere in the lookahead window. Input without one -- an
unbroken digit run, a pure-punctuation blob, unspaced CJK -- has no safe cut point.
`read_chunks` then falls back to a merely UTF-8-safe cut and increments
`unsafe_boundary_cuts`, which is carried into every results row. On PG-19 this count
is zero at every chunk size and every tokenizer.

---

## 5. Smaller corrections

* **`xz --block-size` at `-T1`.** The original always passed `--block-size`. xz will
  split into independent blocks even single-threaded, and each block restarts the
  dictionary -- which would have quietly cost ratio on exactly the `threads=1` cells
  that exist to be the clean baseline for the `-T` speedup curve. It is now passed
  only when `threads > 1`.
* **`resource.getrusage` is Unix-only**, so peak RSS is sampled from the child
  process tree via `psutil`. Without `psutil` the field is recorded as `null`, never
  guessed.
* **`os.sched_getaffinity` and `/proc/meminfo` do not exist on Windows**; both are
  capability-guarded in `resources.py`.
* **`gzip` is commonly installed but not on PATH on Windows** (Git for Windows ships
  it under `usr\bin`). Tool resolution searches PATH then a list of well-known
  install locations and reports the absolute path it settled on.
* **The `leb128_selftest` was correct.** The vectorized NumPy pack/unpack that
  the design spec flagged as never-executed passes 50,000 random values across the full
  21-bit range, all byte-width boundaries, every tokenizer's exact max id,
  random-length arrays, split-stream continuity at every offset, and byte-for-byte
  agreement with the pure-Python fallback. **No bug found** -- the reasoning behind it
  held up.
* **The matrix as literally specified is ~8,100 valid cells per tier**, which at this
  machine's measured throughput is weeks per tier. See `matrix.py`'s module docstring
  for the ratio-grid / performance-OFAT split used instead.
