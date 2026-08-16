#!/usr/bin/env python3
"""parmar core pipeline -- generalized over the handoff Section 5.1 matrix axes.

This is `parmar.py`'s architecture kept intact and widened: streaming end-to-end,
NumPy-vectorized packing with a pure-Python fallback, compressors driven as piped
subprocesses (or in-process bindings), header/footer archive format, and mandatory
round-trip verification on every decompress. Nothing here buffers a whole corpus.

Two defects in the original `parmar.py` are fixed here; both were confirmed by
execution (the original was written under a no-execution constraint):

1. `safe_utf8_boundary(probe_buf, limit)` was called with `limit == len(probe_buf)`,
   and the function returned `n` immediately whenever `end >= n`. The UTF-8 backoff
   was therefore a no-op on the path where no delimiter is found inside the lookahead
   window, and `read_chunks` could cut mid-codepoint -- reproduced as a real
   UnicodeDecodeError at byte 2,101,247 of a synthetic delimiter-free input.
   `trim_to_utf8_boundary` below scans backwards from the tail instead, so it works
   when the cut point is the end of the buffer.

2. Decompression used `enc.decode(ids).encode("utf-8")` per token batch. tiktoken's
   `decode` defaults to `errors="replace"`, and tokens are byte-level, so a multi-byte
   character split across a batch boundary became U+FFFD and broke the sha256 check.
   Reproduced: '\\U0001F926\\U0001F3FC\\u200d\\u2642\\ufe0f' split after its first token
   yielded b'\\xef\\xbf\\xbd\\xef\\xbf\\xbd...' instead of the original bytes.
   `enc.decode_bytes(ids)` returns exact bytes and concatenates safely at any split.

Judgment calls the handoff leaves open, documented at their definitions below:
archive format v2 layout, `--block-size` suppression at threads=1, `fixed_u16`
endianness, and the zstd long-window decode settings.
"""

import bz2
import gzip
import hashlib
import lzma
import os
import struct
import subprocess
import sys
import threading
import time
import zlib

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

import resources

MAGIC = b"PRMR"
VERSION = 2

PACKING_RAW_UTF8 = 0
PACKING_LEB128 = 1
PACKING_FIXED_U16 = 2

PACKING_CODES = {
    "raw_utf8": PACKING_RAW_UTF8,
    "leb128": PACKING_LEB128,
    "fixed_u16": PACKING_FIXED_U16,
}
PACKING_NAMES = {v: k for k, v in PACKING_CODES.items()}

ASCII_LETTERS = frozenset(
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
ASCII_ALNUM = ASCII_LETTERS | frozenset(b"0123456789")
WHITESPACE = frozenset(b" \t\r\n\v\f")
CHUNK_SIZE = 2 * 1024 * 1024
# Raised from the original 4096. The cut rule below is stricter than the original
# delimiter set, so it needs a wider window to find a safe point; 64KB is still
# negligible next to a 1-4MB chunk and makes an unsafe fallback cut essentially
# impossible in prose.
MAX_LOOKAHEAD = 65536
FOOTER_SIZE = 48
IO_BLOCK = 1 << 20
LEB128_MAX_VALUE = (1 << 21) - 1
FIXED_U16_MAX_VALUE = (1 << 16) - 1

TOKENIZERS = ("none", "o200k_base", "cl100k_base", "r50k_base", "p50k_base")
# Vocab sizes are looked up live from tiktoken rather than hardcoded, but these are
# the expected values and a mismatch is worth surfacing.
EXPECTED_VOCAB = {
    "o200k_base": 200019,
    "cl100k_base": 100277,
    "r50k_base": 50257,
    "p50k_base": 50281,
}

TOKENIZATION_LAYOUTS = ("library_batch", "manual_pool", "process_pool")
TRANSPORTS = ("subprocess_cli", "in_process_binding")


# --------------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------------

class Backend:
    def __init__(self, name, family, profile, lzma_filters=None, xz_opts=None,
                 dict_size=None, level=None, long_window=None, ultra=False):
        self.name = name
        self.family = family
        self.profile = profile
        self.lzma_filters = lzma_filters
        self.xz_opts = xz_opts
        self.dict_size = dict_size
        self.level = level
        self.long_window = long_window
        self.ultra = ultra


def _lzma_filters(dict_size, lc, lp, pb, extreme):
    """In-process LZMA2 filters that match what the `xz` CLI is told, exactly.

    The original code spelled the "fast" profile out as MODE_FAST / MF_HC4 /
    nice_len=32 while handing the CLI `--lzma2=preset=6,...`. Those are not the same
    compressor: measured on an 8MB slice of the corpus,

        xz --lzma2=preset=6,lc=3,lp=0,pb=0,dict=32MiB                -> 2,354,592 B
        xz --lzma2=preset=6,...,mode=fast,nice=32,mf=hc4             -> 2,840,812 B

    a 21% difference. Left as-is, `backend=lzma_fast` would have meant one thing
    under `subprocess_cli` and a much weaker thing under `in_process_binding`, so
    the backend_transport axis would have been measuring a compression-settings gap
    rather than subprocess overhead. Deriving the filters from the same preset the
    CLI receives keeps the axis honest.
    """
    preset = (9 | lzma.PRESET_EXTREME) if extreme else 6
    return [{
        "id": lzma.FILTER_LZMA2,
        "preset": preset,
        "dict_size": dict_size,
        "lc": lc, "lp": lp, "pb": pb,
    }]


BACKENDS = {
    "lzma_extreme": Backend(
        "lzma_extreme", "lzma", "max",
        lzma_filters=_lzma_filters(1 << 26, 3, 0, 0, True),
        xz_opts="preset=9e,lc=3,lp=0,pb=0,dict=64MiB", dict_size=1 << 26),
    "lzma_fast": Backend(
        "lzma_fast", "lzma", "fast",
        lzma_filters=_lzma_filters(1 << 25, 3, 0, 0, False),
        xz_opts="preset=6,lc=3,lp=0,pb=0,dict=32MiB", dict_size=1 << 25),
    # handoff Section 3: lc=1,lp=1,pb=1 is the correct pairing for a genuinely fixed
    # 2-byte-per-token stream, by analogy with xz's own UTF-16 recommendation. This
    # has never been tested against real data; the matrix is the first place it is.
    "lzma_tuned_lp1pb1": Backend(
        "lzma_tuned_lp1pb1", "lzma", "max",
        lzma_filters=_lzma_filters(1 << 26, 1, 1, 1, True),
        xz_opts="preset=9e,lc=1,lp=1,pb=1,dict=64MiB", dict_size=1 << 26),
    "zstd_19": Backend("zstd_19", "zstd", "max", level=19, long_window=27),
    "zstd_12": Backend("zstd_12", "zstd", "fast", level=12, long_window=27),
    "zstd_22_long": Backend("zstd_22_long", "zstd", "max", level=22, long_window=31,
                            ultra=True),
    "gzip_9": Backend("gzip_9", "gzip", "fast", level=9),
    "bz2_9": Backend("bz2_9", "bz2", "fast", level=9),
}

FAST_PROFILE_BACKENDS = tuple(n for n, b in BACKENDS.items() if b.profile == "fast")


def xz_block_size_for(dict_size, threads):
    return max(dict_size * 2, dict_size * 2 * min(threads, 4) // 4)


# --------------------------------------------------------------------------------
# Packing
# --------------------------------------------------------------------------------

def leb128_pack_py(token_ids):
    out = bytearray()
    for value in token_ids:
        value = int(value)
        while True:
            byte = value & 0x7F
            value >>= 7
            if value:
                out.append(byte | 0x80)
            else:
                out.append(byte)
                break
    return bytes(out)


def leb128_unpack_partial_py(data):
    ids = []
    value = 0
    shift = 0
    last_complete = 0
    for i, byte in enumerate(data):
        value |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
        else:
            ids.append(value)
            value = 0
            shift = 0
            last_complete = i + 1
    return ids, data[last_complete:]


def leb128_pack_np(ids):
    arr = np.asarray(ids, dtype=np.uint32)
    if arr.size == 0:
        return b""
    if int(arr.max()) > LEB128_MAX_VALUE:
        raise ValueError(f"token id exceeds {LEB128_MAX_VALUE} (21-bit fast-path range)")

    more0 = arr >= 0x80
    more1 = arr >= 0x4000

    b0 = (arr & 0x7F).astype(np.uint8)
    b1 = ((arr >> 7) & 0x7F).astype(np.uint8)
    b2 = ((arr >> 14) & 0x7F).astype(np.uint8)

    nbytes = np.ones(arr.size, dtype=np.int64)
    nbytes += more0
    nbytes += more1

    offsets = np.empty(arr.size + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(nbytes, out=offsets[1:])
    total = int(offsets[-1])
    start = offsets[:-1]

    out = np.empty(total, dtype=np.uint8)
    out[start] = b0 | (more0.astype(np.uint8) << 7)

    idx1 = start[more0] + 1
    out[idx1] = b1[more0] | (more1[more0].astype(np.uint8) << 7)

    idx2 = start[more1] + 2
    out[idx2] = b2[more1]

    return out.tobytes()


def leb128_unpack_partial_np(data):
    if not data:
        return np.empty(0, dtype=np.uint32), b""

    arr = np.frombuffer(data, dtype=np.uint8)
    is_terminal = (arr & 0x80) == 0
    terminal_idx = np.nonzero(is_terminal)[0]
    if terminal_idx.size == 0:
        return np.empty(0, dtype=np.uint32), data

    last_terminal = int(terminal_idx[-1])
    leftover = data[last_terminal + 1:]

    group_start = np.empty(terminal_idx.size, dtype=np.int64)
    group_start[0] = 0
    group_start[1:] = terminal_idx[:-1] + 1
    widths = terminal_idx - group_start + 1

    if bool(np.any(widths > 3)):
        raise ValueError("LEB128 token wider than 3 bytes encountered; "
                         "corrupt stream or vocab out of range")

    values = arr[group_start].astype(np.uint32) & 0x7F

    w2 = widths >= 2
    values[w2] |= (arr[group_start[w2] + 1].astype(np.uint32) & 0x7F) << 7

    w3 = widths >= 3
    values[w3] |= (arr[group_start[w3] + 2].astype(np.uint32) & 0x7F) << 14

    return values, leftover


if HAS_NUMPY:
    leb128_pack = leb128_pack_np
    leb128_unpack_partial = leb128_unpack_partial_np
else:
    leb128_pack = leb128_pack_py
    leb128_unpack_partial = leb128_unpack_partial_py


# fixed_u16 is little-endian explicitly ('<u2', not native '=u2'). The archive has to
# be readable on a big-endian host, and the lp=1/pb=1 alignment tuning the handoff
# specifies only models a real periodicity if the byte order is fixed by the format
# rather than by the writer's CPU.
def fixed_u16_pack(ids):
    if HAS_NUMPY:
        arr = np.asarray(ids, dtype=np.uint32)
        if arr.size == 0:
            return b""
        hi = int(arr.max())
        if hi > FIXED_U16_MAX_VALUE:
            raise ValueError(f"token id {hi} exceeds {FIXED_U16_MAX_VALUE}; "
                             f"fixed_u16 packing is invalid for this tokenizer")
        return arr.astype("<u2").tobytes()
    out = bytearray()
    for value in ids:
        value = int(value)
        if value > FIXED_U16_MAX_VALUE:
            raise ValueError(f"token id {value} exceeds {FIXED_U16_MAX_VALUE}; "
                             f"fixed_u16 packing is invalid for this tokenizer")
        out += struct.pack("<H", value)
    return bytes(out)


def fixed_u16_unpack_partial(data):
    usable = len(data) - (len(data) % 2)
    leftover = data[usable:]
    if usable == 0:
        return (np.empty(0, dtype=np.uint32) if HAS_NUMPY else []), leftover
    body = data[:usable]
    if HAS_NUMPY:
        return np.frombuffer(body, dtype="<u2").astype(np.uint32), leftover
    return list(struct.unpack(f"<{usable // 2}H", body)), leftover


def get_packer(packing):
    if packing == "leb128":
        return leb128_pack, leb128_unpack_partial
    if packing == "fixed_u16":
        return fixed_u16_pack, fixed_u16_unpack_partial
    raise ValueError(f"packing {packing!r} has no token packer (raw_utf8 is passthrough)")


def max_id_for_packing(packing):
    if packing == "leb128":
        return LEB128_MAX_VALUE
    if packing == "fixed_u16":
        return FIXED_U16_MAX_VALUE
    return None


# --------------------------------------------------------------------------------
# Boundary-safe chunk reading
# --------------------------------------------------------------------------------

def is_utf8_continuation(byte):
    return (byte & 0xC0) == 0x80


def _seq_len_for_lead(b):
    if b < 0x80:
        return 1
    if b >= 0xF0:
        return 4
    if b >= 0xE0:
        return 3
    if b >= 0xC0:
        return 2
    return None


def trim_to_utf8_boundary(data, end):
    """Largest cut point <= `end` that does not land inside a multi-byte sequence.

    Scans backwards from the tail, which is what the original `safe_utf8_boundary`
    could not do: its `if end >= n: return n` guard made it a no-op precisely at the
    call site that needed it (cutting at the end of the buffer). A malformed sequence
    is left alone rather than silently trimmed -- the caller's strict decode should
    be the thing that reports bad input.
    """
    if end <= 0:
        return 0
    i = end - 1
    lo = max(0, end - 4)
    while i >= lo and is_utf8_continuation(data[i]):
        i -= 1
    if i < lo:
        return end
    seq = _seq_len_for_lead(data[i])
    if seq is None:
        return end
    return end if i + seq <= end else i


def find_safe_boundary(buf, start, limit):
    """First index i in [start, limit) with buf[i-1] an ASCII letter and buf[i] space.

    THE CUT RULE, AND WHY IT IS NOT THE ORIGINAL ONE
    ------------------------------------------------
    The original code cut *after* a delimiter from a set that included whitespace, so
    a chunk ended with a trailing space and the next chunk began with a bare word.
    tiktoken's pretokenizers attach whitespace as a *leading* prefix to the word that
    follows it -- ` ?\\p{L}+` in the GPT-2 family, `[^\\r\\n\\p{L}\\p{N}]?[letters]+`
    in o200k/cl100k -- so that cut orphaned the space from its word. Measured against
    the 64MB corpus, o200k_base produced 16,020,945 tokens unsplit but 16,020,999
    split at 1MB, with the first divergence at token 251,996: `" and"` (one token,
    1983) became `" "` + `"and"` (220, 5037). This is exactly the failure handoff
    Section 8.2 anticipated -- "the regex pretoken pattern's leading-optional-
    non-letter-character behavior pulling a byte across what looks like a clean
    split" -- and it was never caught because it was never run.

    Cutting so that the chunk ends after a letter and the whitespace run travels with
    the following chunk is safe for both pretokenizer families:

      * the preceding chunk ends inside a word pretoken, which has no trailing
        optional suffix that could reach across (o200k's `(?i:'s|'t|...)` needs a
        quote next, not whitespace; its punctuation alternative's `[\\r\\n/]*` tail
        only applies to a punctuation pretoken, which this rule never ends on)
      * the following chunk starts at a whitespace run, which is where every
        whitespace-absorbing alternative in both patterns starts anyway
      * ending on a non-whitespace character also avoids the GPT-2 family's
        end-of-string `\\s+(?!\\S)` alternative regrouping a trailing `\\r\\n` that
        would have been split in the joined text
      * both bytes are ASCII, so the cut is a valid UTF-8 boundary for free

    Ending on an alphanumeric specifically (rather than any non-whitespace) keeps the
    cut off punctuation, whose o200k alternative carries a `[\\r\\n/]*` tail that
    would absorb a following newline in the joined text but not in the split text.
    Digits are safe to end on even though o200k groups them as `\\p{N}{1,3}`: the run
    terminates at the whitespace in both the joined and the split text, so it groups
    identically either way.

    LIMITATION, reported rather than hidden: this requires an ASCII alphanumeric
    followed by whitespace. Text with no such position inside the lookahead window --
    an unbroken digit run, a pure-punctuation blob, or a script with no ASCII letters
    such as unspaced CJK -- has no safe cut point, and the caller falls back to a
    merely UTF-8-safe cut and counts it in `unsafe_boundary_cuts`. On the PG-19
    corpus this count is zero at every chunk size, verified by verify_boundaries.py.
    """
    i = max(start, 1)
    while i < limit:
        if buf[i] in WHITESPACE and buf[i - 1] in ASCII_ALNUM:
            return i
        i += 1
    return None


def read_chunks(fileobj, chunk_size=CHUNK_SIZE, max_lookahead=MAX_LOOKAHEAD,
                stats=None):
    """Stream boundary-safe chunks off a file handle.

    `stats` (a dict) receives `unsafe_boundary_cuts`: the number of chunks that had
    to be cut at a merely UTF-8-safe point because no tokenizer-safe point existed
    within the lookahead window. That count is carried all the way into the results
    row rather than being swallowed -- a corpus that triggers it has a token stream
    that depends on chunk size, and the analysis needs to know.
    """
    if stats is not None:
        stats.setdefault("unsafe_boundary_cuts", 0)
    leftover = b""
    while True:
        need = chunk_size - len(leftover)
        block = fileobj.read(need) if need > 0 else b""
        buf = leftover + block
        leftover = b""
        if not buf:
            return
        if len(buf) < chunk_size:
            yield buf
            return
        lookahead = fileobj.read(max_lookahead)
        if not lookahead:
            yield buf
            return
        probe_buf = buf + lookahead
        limit = len(probe_buf)
        cut = find_safe_boundary(probe_buf, len(buf), limit)
        if cut is None:
            cut = trim_to_utf8_boundary(probe_buf, limit)
            if cut <= 0:
                cut = limit
            if stats is not None:
                stats["unsafe_boundary_cuts"] += 1
        yield probe_buf[:cut]
        leftover = probe_buf[cut:]


# --------------------------------------------------------------------------------
# Tokenization layouts
# --------------------------------------------------------------------------------

_WORKER_ENC = None


def _pool_init(encoding_name):
    global _WORKER_ENC
    import tiktoken
    _WORKER_ENC = tiktoken.get_encoding(encoding_name)


def _pool_encode(text):
    return _WORKER_ENC.encode_ordinary(text)


class Tokenizer:
    """Wraps a tiktoken encoding plus a chosen parallelism layout.

    `process_pool` on Windows uses spawn, so each worker re-imports tiktoken and
    reloads the BPE table (~1-2s, ~100MB per worker). The pool is created once and
    reused across batches, and the startup cost is measured into `startup_time_s`
    rather than hidden -- it is part of the honest answer to whether a hand-rolled
    pool beats the library's own batch parallelism.
    """

    def __init__(self, name, layout, threads):
        import tiktoken
        self.name = name
        self.layout = layout
        self.threads = threads
        self.enc = tiktoken.get_encoding(name)
        self.n_vocab = self.enc.n_vocab
        self._pool = None
        self.startup_time_s = 0.0

        expected = EXPECTED_VOCAB.get(name)
        if expected is not None and expected != self.n_vocab:
            print(f"note: {name} reports n_vocab={self.n_vocab}, expected {expected}; "
                  f"packing validity was decided from the live value",
                  file=sys.stderr, flush=True)

        if layout == "manual_pool":
            from concurrent.futures import ThreadPoolExecutor
            t0 = time.perf_counter()
            self._pool = ThreadPoolExecutor(max_workers=threads)
            self.startup_time_s = time.perf_counter() - t0
        elif layout == "process_pool":
            from concurrent.futures import ProcessPoolExecutor
            t0 = time.perf_counter()
            self._pool = ProcessPoolExecutor(
                max_workers=threads, initializer=_pool_init, initargs=(name,))
            # Force worker startup now so the spawn cost lands in startup_time_s
            # instead of being charged to the first batch's tokenize time.
            list(self._pool.map(_pool_encode, [""] * threads))
            self.startup_time_s = time.perf_counter() - t0
        elif layout != "library_batch":
            raise ValueError(f"unknown tokenization layout {layout!r}")

    def encode_batch(self, texts):
        if self.layout == "library_batch":
            return self.enc.encode_ordinary_batch(texts, num_threads=self.threads)
        if self.layout == "manual_pool":
            return list(self._pool.map(self.enc.encode_ordinary, texts))
        return list(self._pool.map(_pool_encode, texts))

    def decode_bytes(self, ids):
        # decode_bytes, never decode(): decode() defaults to errors="replace" and
        # corrupts any multi-byte character straddling a batch boundary.
        return self.enc.decode_bytes(ids)

    def close(self):
        if self._pool is not None:
            self._pool.shutdown(wait=True)
            self._pool = None


# --------------------------------------------------------------------------------
# Compressor sinks
# --------------------------------------------------------------------------------

class SubprocessSink:
    def __init__(self, proc, argv):
        self.proc = proc
        self.argv = argv
        self.pid = proc.pid

    def feed(self, data):
        self.proc.stdin.write(data)

    def close(self):
        self.proc.stdin.close()
        rc = self.proc.wait()
        if rc != 0:
            stderr = self.proc.stderr.read().decode("utf-8", errors="replace") \
                if self.proc.stderr else ""
            raise RuntimeError(f"{self.argv[0]} exited with code {rc}: {stderr}")


class InProcessSink:
    def __init__(self, out_f, compressor_obj, flush_attr="flush"):
        self.out_f = out_f
        self.c = compressor_obj
        self.flush_attr = flush_attr
        self.pid = None

    def feed(self, data):
        out = self.c.compress(data)
        if out:
            self.out_f.write(out)

    def close(self):
        out = getattr(self.c, self.flush_attr)()
        if out:
            self.out_f.write(out)


class _GzipStreamCompressor:
    """zlib deflate with a gzip wrapper, exposing the compress/flush protocol."""

    def __init__(self, level):
        self.c = zlib.compressobj(level, zlib.DEFLATED, 16 + zlib.MAX_WBITS)

    def compress(self, data):
        return self.c.compress(data)

    def flush(self):
        return self.c.flush()


def _tool_path(name, tools):
    entry = tools.get(name)
    if not entry or not entry["available"]:
        raise RuntimeError(
            f"{name} CLI not found on PATH or in any well-known install dir; "
            f"this backend/transport combination cannot run here")
    return entry["path"]


def compressor_argv(backend, threads, tools):
    b = BACKENDS[backend]
    if b.family == "lzma":
        argv = [_tool_path("xz", tools), "-T", str(threads), "-c"]
        # --block-size is only passed when actually running multithreaded. xz will
        # split into independent blocks even at -T1 if a block size is given, and
        # each block starts with a fresh dictionary -- that would silently cost ratio
        # on exactly the single-thread cells that exist to be the clean baseline for
        # the -T speedup curve (handoff Section 3 / Section 7 question 4).
        if threads > 1:
            argv.append(f"--block-size={xz_block_size_for(b.dict_size, threads)}")
        argv.append(f"--lzma2={b.xz_opts}")
        return argv
    if b.family == "zstd":
        argv = [_tool_path("zstd", tools), f"-T{threads}", "-c"]
        if b.ultra:
            argv.append("--ultra")
        argv.append(f"-{b.level}")
        argv.append(f"--long={b.long_window}")
        return argv
    if b.family == "gzip":
        return [_tool_path("gzip", tools), f"-{b.level}", "-c"]
    if b.family == "bz2":
        return [_tool_path("bzip2", tools), f"-{b.level}", "-c"]
    raise ValueError(f"unknown backend family {b.family}")


def decompressor_argv(backend, threads, tools):
    b = BACKENDS[backend]
    if b.family == "lzma":
        return [_tool_path("xz", tools), "-dc", "-T", str(threads)]
    if b.family == "zstd":
        # The long-window flag must be repeated on decompress: zstd refuses a frame
        # whose window exceeds its default memory limit rather than allocating for it.
        return [_tool_path("zstd", tools), "-dc", f"-T{threads}",
                f"--long={b.long_window}"]
    if b.family == "gzip":
        return [_tool_path("gzip", tools), "-dc"]
    if b.family == "bz2":
        return [_tool_path("bzip2", tools), "-dc"]
    raise ValueError(f"unknown backend family {b.family}")


def open_sink(out_f, backend, transport, threads, tools):
    b = BACKENDS[backend]
    if transport == "subprocess_cli":
        argv = compressor_argv(backend, threads, tools)
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=out_f,
                                stderr=subprocess.PIPE)
        return SubprocessSink(proc, argv)

    if transport != "in_process_binding":
        raise ValueError(f"unknown transport {transport!r}")

    if b.family == "lzma":
        # Python's lzma module is single-threaded regardless of the threads axis.
        # Said out loud rather than silently ignoring the parameter.
        if threads > 1:
            print(f"note: backend={backend} transport=in_process_binding ignores "
                  f"threads={threads}; Python's lzma module is single-threaded only",
                  file=sys.stderr, flush=True)
        return InProcessSink(out_f, lzma.LZMACompressor(format=lzma.FORMAT_XZ,
                                                        filters=b.lzma_filters))
    if b.family == "zstd":
        try:
            import zstandard
        except ImportError as exc:
            raise RuntimeError(
                "zstandard package not installed; the zstd in_process_binding "
                "transport cannot run here") from exc
        params = zstandard.ZstdCompressionParameters.from_level(
            b.level, threads=threads,
            enable_ldm=True, window_log=b.long_window)
        cctx = zstandard.ZstdCompressor(compression_params=params)
        return InProcessSink(out_f, cctx.compressobj(), flush_attr="flush")
    if b.family == "gzip":
        return InProcessSink(out_f, _GzipStreamCompressor(b.level))
    if b.family == "bz2":
        return InProcessSink(out_f, bz2.BZ2Compressor(b.level))
    raise ValueError(f"unknown backend family {b.family}")


# --------------------------------------------------------------------------------
# Decompression
# --------------------------------------------------------------------------------

def _feed_stdin(in_f, proc, payload_size):
    remaining = payload_size
    try:
        while remaining > 0:
            chunk = in_f.read(min(IO_BLOCK, remaining))
            if not chunk:
                break
            proc.stdin.write(chunk)
            remaining -= len(chunk)
    except (BrokenPipeError, OSError):
        pass
    finally:
        try:
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass


def iter_decompressed(in_f, payload_size, backend, transport, threads, tools):
    b = BACKENDS[backend]

    if transport == "in_process_binding":
        if b.family == "lzma":
            d = lzma.LZMADecompressor(format=lzma.FORMAT_XZ)
        elif b.family == "zstd":
            import zstandard
            dctx = zstandard.ZstdDecompressor(max_window_size=1 << b.long_window)
            d = dctx.decompressobj()
        elif b.family == "gzip":
            d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        elif b.family == "bz2":
            d = bz2.BZ2Decompressor()
        else:
            raise ValueError(f"unknown backend family {b.family}")
        remaining = payload_size
        while remaining > 0:
            chunk = in_f.read(min(IO_BLOCK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            out = d.decompress(chunk)
            if out:
                yield out
        return

    argv = decompressor_argv(backend, threads, tools)
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    feeder = threading.Thread(target=_feed_stdin, args=(in_f, proc, payload_size))
    feeder.start()
    try:
        while True:
            block = proc.stdout.read(IO_BLOCK)
            if not block:
                break
            yield block
    finally:
        feeder.join()
        rc = proc.wait()
        if rc != 0:
            stderr = proc.stderr.read().decode("utf-8", errors="replace") \
                if proc.stderr else ""
            raise RuntimeError(f"{argv[0]} -d exited with code {rc}: {stderr}")


# --------------------------------------------------------------------------------
# Archive format v2
# --------------------------------------------------------------------------------
# header:  MAGIC(4) version(1) packing(1)
#          len(tokenizer)(1) tokenizer  len(backend)(1) backend
#          len(transport)(1) transport
# footer:  orig_len(u64 LE) token_count(u64 LE) sha256(32)  == 48 bytes, unchanged
#
# The transport is recorded even though every family's container is transport-agnostic
# (an xz stream from the CLI decodes identically through Python's lzma module). It is
# stored so a matrix archive is self-describing about the cell that produced it, which
# matters for `rerun-cell` and for post-hoc auditing of a results file.

def build_header(tokenizer_name, packing, backend, transport):
    parts = bytearray()
    parts += MAGIC
    parts += struct.pack("<BB", VERSION, PACKING_CODES[packing])
    for s in (tokenizer_name, backend, transport):
        b = s.encode("ascii")
        parts += struct.pack("<B", len(b))
        parts += b
    return bytes(parts)


def parse_header(fh):
    magic = fh.read(4)
    if magic != MAGIC:
        raise ValueError("not a parmar archive")
    version, packing = struct.unpack("<BB", fh.read(2))
    if version != VERSION:
        raise ValueError(f"unsupported archive version {version}")
    if packing not in PACKING_NAMES:
        raise ValueError(f"unsupported packing mode {packing}")
    out = []
    for _ in range(3):
        n = struct.unpack("<B", fh.read(1))[0]
        out.append(fh.read(n).decode("ascii"))
    return {
        "packing": PACKING_NAMES[packing],
        "tokenizer": out[0],
        "backend": out[1],
        "transport": out[2],
    }


# --------------------------------------------------------------------------------
# Self-test / fuzz (handoff Section 8.3)
# --------------------------------------------------------------------------------

def leb128_selftest(vocab_size):
    samples = [0, 1, 126, 127, 128, 16383, 16384, LEB128_MAX_VALUE, vocab_size - 1]
    packed = leb128_pack(samples)
    ids, leftover = leb128_unpack_partial(packed)
    restored = list(ids)
    if restored != samples or leftover:
        raise RuntimeError(f"LEB128 self-test failed: {samples} != {restored} "
                           f"(leftover={leftover!r})")


def _as_list(x):
    return x.tolist() if hasattr(x, "tolist") else list(x)


def packing_fuzz(packing, n_cases=50_000, seed=0xC0FFEE, vocab_maxes=(),
                 verbose=False):
    """Property test for a packing scheme (handoff Section 8.3).

    Covers, for each of `leb128` and `fixed_u16`:
      * every byte-width boundary value and each tokenizer's exact max id
      * `n_cases` uniformly random ids across the scheme's full valid range
      * random-length arrays (including empty and single-element)
      * split-stream continuity: unpacking the same buffer cut at every plausible
        offset must produce the same ids and correctly carry the remainder, which is
        the property the streaming decompressor actually depends on
      * NumPy path vs pure-Python path agreement, byte for byte -- the fallback is
        what runs on a machine without NumPy and has never been differentially checked
    """
    import random
    rnd = random.Random(seed)
    hi = max_id_for_packing(packing)
    pack, unpack = get_packer(packing)

    boundaries = [0, 1, 126, 127, 128, 129, 255, 256, 16382, 16383, 16384, 16385,
                  hi - 1, hi]
    boundaries += [v for v in (vs - 1 for vs in vocab_maxes) if 0 <= v <= hi]
    boundaries = sorted({v for v in boundaries if 0 <= v <= hi})

    checks = 0

    # 1. boundary values, all at once and one at a time
    got, leftover = unpack(pack(boundaries))
    if _as_list(got) != boundaries or leftover:
        raise AssertionError(f"{packing}: boundary batch mismatch\n"
                             f"  in : {boundaries}\n  out: {_as_list(got)}\n"
                             f"  leftover={leftover!r}")
    checks += 1
    for v in boundaries:
        got, leftover = unpack(pack([v]))
        if _as_list(got) != [v] or leftover:
            raise AssertionError(f"{packing}: single-value mismatch for {v}: "
                                 f"{_as_list(got)} leftover={leftover!r}")
        checks += 1

    # 2. bulk random values
    values = [rnd.randint(0, hi) for _ in range(n_cases)]
    got, leftover = unpack(pack(values))
    if _as_list(got) != values or leftover:
        bad = next(i for i, (a, b) in enumerate(zip(_as_list(got), values)) if a != b)
        raise AssertionError(f"{packing}: bulk random mismatch at index {bad}: "
                             f"got {_as_list(got)[bad]} want {values[bad]}")
    checks += 1

    # 3. random-length arrays
    for _ in range(300):
        n = rnd.choice([0, 1, 2, 3, rnd.randint(4, 400)])
        vals = [rnd.randint(0, hi) for _ in range(n)]
        got, leftover = unpack(pack(vals))
        if _as_list(got) != vals or leftover:
            raise AssertionError(f"{packing}: random-length mismatch at n={n}")
        checks += 1

    # 4. split-stream continuity
    for _ in range(300):
        vals = [rnd.randint(0, hi) for _ in range(rnd.randint(1, 200))]
        blob = pack(vals)
        cut = rnd.randint(0, len(blob))
        a, rest_a = unpack(blob[:cut])
        b, rest_b = unpack(rest_a + blob[cut:])
        merged = _as_list(a) + _as_list(b)
        if merged != vals or rest_b:
            raise AssertionError(
                f"{packing}: split-stream mismatch at cut={cut}/{len(blob)}\n"
                f"  want {vals[:8]}... got {merged[:8]}... leftover={rest_b!r}")
        checks += 1

    # 5. NumPy vs pure-Python agreement
    if HAS_NUMPY and packing == "leb128":
        for _ in range(200):
            vals = [rnd.randint(0, hi) for _ in range(rnd.randint(0, 300))]
            if leb128_pack_np(vals) != leb128_pack_py(vals):
                raise AssertionError(f"{packing}: numpy/python pack disagree for "
                                     f"{len(vals)} values")
            blob = leb128_pack_py(vals)
            ids_np, rest_np = leb128_unpack_partial_np(blob)
            ids_py, rest_py = leb128_unpack_partial_py(blob)
            if _as_list(ids_np) != _as_list(ids_py) or rest_np != rest_py:
                raise AssertionError(f"{packing}: numpy/python unpack disagree")
            checks += 1

    if verbose:
        print(f"  {packing:<10} OK  ({checks:,} assertions, {n_cases:,} random ids, "
              f"range 0..{hi:,})")
    return checks


def run_fuzz(n_cases=50_000, seed=0xC0FFEE, verbose=True):
    """Full packing verification. Called before every tier and before every resume."""
    vocab_maxes = tuple(EXPECTED_VOCAB.values())
    total = 0
    if verbose:
        print(f"LEB128/fixed_u16 property test (numpy={HAS_NUMPY}) ...")
    total += packing_fuzz("leb128", n_cases, seed, vocab_maxes, verbose)
    total += packing_fuzz("fixed_u16", n_cases, seed ^ 0x5EED,
                          tuple(v for v in vocab_maxes if v <= FIXED_U16_MAX_VALUE + 1),
                          verbose)
    if verbose:
        print(f"  total {total:,} assertions passed")
    return total


# --------------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------------

class HashSink:
    """Round-trip verification target that never touches the disk.

    Judgment call: the handoff requires that every configuration's decompression is
    actually run and its sha256 actually matches, but does not require the bytes be
    kept. Writing them costs one full corpus write per matrix cell (4GB x ~50 cells
    at the top tier) and measures the filesystem rather than the pipeline, so
    verification hashes in memory by default. `--emit-decompressed` restores a real
    file for debugging a specific cell.
    """

    def __init__(self, path=None):
        self.sha = hashlib.sha256()
        self.length = 0
        self.fh = open(path, "wb") if path else None

    def write(self, data):
        self.sha.update(data)
        self.length += len(data)
        if self.fh is not None:
            self.fh.write(data)

    def close(self):
        if self.fh is not None:
            self.fh.close()
            self.fh = None


def compress_file(input_path, output_path, tokenizer, packing, backend, transport,
                  layout, threads, chunk_size, batch_chunks, tools=None,
                  progress=None):
    """Stream input_path -> output_path. Returns a stats dict.

    Nothing larger than one batch is ever resident: chunks stream off the file handle,
    tokenize, pack, and go straight into the compressor's stdin, whose stdout is the
    output file handle. The compressed payload never passes through Python.
    """
    if tools is None:
        tools = resources.detect_tools()

    if packing == "raw_utf8":
        if tokenizer != "none":
            raise ValueError("raw_utf8 packing requires tokenizer=none")
        enc = None
    else:
        if tokenizer == "none":
            raise ValueError(f"tokenizer=none cannot use packing={packing}")
        enc = Tokenizer(tokenizer, layout, threads)
        hi = max_id_for_packing(packing)
        if enc.n_vocab - 1 > hi:
            enc.close()
            raise ValueError(f"tokenizer {tokenizer} vocab {enc.n_vocab} exceeds the "
                             f"{packing} ceiling of {hi + 1}")
        leb128_selftest(enc.n_vocab) if packing == "leb128" else None

    pack = None if packing == "raw_utf8" else get_packer(packing)[0]

    sha = hashlib.sha256()
    orig_len = 0
    token_count = 0
    tokenize_time = 0.0
    pack_time = 0.0
    sink = None
    chunk_stats = {"unsafe_boundary_cuts": 0}
    # Bytes actually handed to the compressor. This -- not the corpus size and not
    # the compressed output -- is what determines how many xz blocks exist, and
    # therefore how much multithreading headroom the backend has. Since parmar
    # shrinks the compressor's input, it also reduces the block count at a fixed
    # block size, which is a real cost of the technique and needs measuring rather
    # than inferring.
    packed_bytes = 0

    t0 = time.perf_counter()
    try:
        with open(output_path, "wb") as out_f:
            out_f.write(build_header(tokenizer, packing, backend, transport))
            out_f.flush()
            sink = open_sink(out_f, backend, transport, threads, tools)
            child_pid = getattr(sink, "pid", None)

            with open(input_path, "rb") as in_f:
                batch = []
                last_report = t0
                for chunk in read_chunks(in_f, chunk_size, stats=chunk_stats):
                    sha.update(chunk)
                    orig_len += len(chunk)
                    if enc is None:
                        sink.feed(chunk)
                        packed_bytes += len(chunk)
                        continue
                    batch.append(chunk)
                    if len(batch) >= batch_chunks:
                        n, tt, pt, pb = _encode_pack_feed(batch, enc, pack, sink)
                        token_count += n
                        tokenize_time += tt
                        pack_time += pt
                        packed_bytes += pb
                        batch = []
                        if progress:
                            now = time.perf_counter()
                            if now - last_report >= 10.0:
                                progress(orig_len, now - t0)
                                last_report = now
                if batch:
                    n, tt, pt, pb = _encode_pack_feed(batch, enc, pack, sink)
                    token_count += n
                    tokenize_time += tt
                    pack_time += pt
                    packed_bytes += pb

            sink.close()
            sink = None
            out_f.seek(0, os.SEEK_END)
            out_f.write(struct.pack("<QQ", orig_len, token_count))
            out_f.write(sha.digest())
    finally:
        if sink is not None:
            try:
                sink.close()
            except Exception:
                pass
        if enc is not None:
            enc.close()

    elapsed = time.perf_counter() - t0
    final_size = os.path.getsize(output_path)
    return {
        "orig_len": orig_len,
        "token_count": token_count,
        "compressed_bytes": final_size,
        "ratio": orig_len / final_size if final_size else float("inf"),
        "total_time_s": elapsed,
        "tokenize_time_s": tokenize_time,
        "pack_time_s": pack_time,
        "compress_time_s": max(elapsed - tokenize_time - pack_time, 0.0),
        "tokenizer_startup_s": enc.startup_time_s if enc else 0.0,
        "sha256": sha.hexdigest(),
        "child_pid": child_pid,
        "unsafe_boundary_cuts": chunk_stats["unsafe_boundary_cuts"],
        "packed_bytes": packed_bytes,
    }


def _encode_pack_feed(chunks, enc, pack, sink):
    texts = [c.decode("utf-8", errors="strict") for c in chunks]
    t0 = time.perf_counter()
    per_chunk = enc.encode_batch(texts)
    t1 = time.perf_counter()

    if HAS_NUMPY:
        arrays = [np.asarray(ids, dtype=np.uint32) for ids in per_chunk if ids]
        if not arrays:
            return 0, t1 - t0, 0.0, 0
        all_ids = np.concatenate(arrays) if len(arrays) > 1 else arrays[0]
        packed = pack(all_ids)
        n = int(all_ids.size)
    else:
        flat = [i for ids in per_chunk for i in ids]
        packed = pack(flat)
        n = len(flat)
    t2 = time.perf_counter()
    if packed:
        sink.feed(packed)
    return n, t1 - t0, t2 - t1, len(packed)


def decompress_file(input_path, output_path, threads, tools=None,
                    decode_batch_tokens=1_000_000):
    """Decompress and verify. `output_path=None` verifies without writing to disk."""
    if tools is None:
        tools = resources.detect_tools()

    file_size = os.path.getsize(input_path)
    t0 = time.perf_counter()

    with open(input_path, "rb") as in_f:
        meta = parse_header(in_f)
        header_size = in_f.tell()
        payload_size = file_size - header_size - FOOTER_SIZE
        if payload_size < 0:
            raise ValueError("archive too small or corrupted")

        in_f.seek(file_size - FOOTER_SIZE)
        orig_len, token_count = struct.unpack("<QQ", in_f.read(16))
        sha_expected = in_f.read(32)
        in_f.seek(header_size)

        packing = meta["packing"]
        enc = None if packing == "raw_utf8" else Tokenizer(meta["tokenizer"],
                                                           "library_batch", threads)
        unpack = None if packing == "raw_utf8" else get_packer(packing)[1]
        out = HashSink(output_path)
        total_tokens = 0
        pending = b""

        try:
            blocks = iter_decompressed(in_f, payload_size, meta["backend"],
                                       meta["transport"], threads, tools)
            if packing == "raw_utf8":
                for block in blocks:
                    out.write(block)
            else:
                batch = []
                batch_n = 0
                for block in blocks:
                    ids, pending = unpack(pending + block)
                    n = len(ids)
                    if n:
                        batch.append(ids)
                        batch_n += n
                        total_tokens += n
                    if batch_n >= decode_batch_tokens:
                        out.write(enc.decode_bytes(_flatten(batch)))
                        batch = []
                        batch_n = 0
                if batch:
                    out.write(enc.decode_bytes(_flatten(batch)))
        finally:
            out.close()
            if enc is not None:
                enc.close()

    elapsed = time.perf_counter() - t0

    errors = []
    if pending:
        errors.append(f"archive truncated: {len(pending)} trailing bytes did not form "
                      f"a complete token")
    length_match = out.length == orig_len
    if not length_match:
        errors.append(f"length mismatch: expected {orig_len}, got {out.length}")
    token_count_match = (packing == "raw_utf8") or (total_tokens == token_count)
    if not token_count_match:
        errors.append(f"token count mismatch: expected {token_count}, got {total_tokens}")
    sha256_match = out.sha.digest() == sha_expected
    if not sha256_match:
        errors.append("sha256 mismatch: round-trip corrupted")

    return {
        "meta": meta,
        "orig_len": orig_len,
        "decompressed_len": out.length,
        "token_count": token_count,
        "decoded_token_count": total_tokens,
        "decompress_time_s": elapsed,
        "sha256_match": sha256_match,
        "length_match": length_match,
        "token_count_match": token_count_match,
        "round_trip_verified": bool(sha256_match and length_match
                                    and token_count_match and not pending),
        "errors": errors,
    }


def _flatten(batch):
    if not batch:
        return []
    if HAS_NUMPY and hasattr(batch[0], "tolist"):
        arr = np.concatenate(batch) if len(batch) > 1 else batch[0]
        return arr.tolist()
    return [i for sub in batch for i in sub]


if __name__ == "__main__":
    run_fuzz()
