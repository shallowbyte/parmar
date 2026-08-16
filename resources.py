#!/usr/bin/env python3
"""Portable resource / capability detection for the parmar harness (handoff Section 6).

Must run unmodified on Kaggle (Linux, cgroup-limited container) and on an arbitrary
local machine including Windows. Every detection path that falls back to a guess says
so out loud -- per the project's ground rule that silent fallbacks are bugs.

Judgment calls documented here because the handoff does not specify them:

* The handoff assumes a POSIX environment (`/proc/meminfo`, `sched_getaffinity`,
  `nproc`/`free -h`/`df -h` for ground-truth checking). All of those are guarded by
  capability checks rather than assumed, so the module degrades explicitly on Windows
  instead of raising.
* `gzip` is frequently installed on Windows but not on PATH (Git for Windows ships it
  under `usr\\bin`, which is not added to PATH by the installer). Rather than declaring
  the gzip backend unavailable, tool resolution searches a short list of well-known
  install locations after PATH and reports the absolute path it settled on. If nothing
  is found the tool is reported missing and dependent matrix cells are skipped with a
  printed reason -- never silently degraded to a different compressor.
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys

CONSERVATIVE_RAM_BYTES = 8 * 1024 ** 3

# Searched after PATH, in order. Covers Git for Windows, MSYS2, Cygwin, scoop and
# Chocolatey shims -- the ways these tools actually end up on a Windows box.
WINDOWS_TOOL_DIRS = (
    r"C:\Program Files\Git\usr\bin",
    r"C:\Program Files\Git\mingw64\bin",
    r"C:\Program Files (x86)\Git\usr\bin",
    r"C:\msys64\usr\bin",
    r"C:\msys64\mingw64\bin",
    r"C:\cygwin64\bin",
    r"C:\ProgramData\chocolatey\bin",
    os.path.expanduser(r"~\scoop\shims"),
)

TOOLS = ("xz", "zstd", "gzip", "bzip2")
PY_LIBS = ("numpy", "tiktoken", "zstandard", "psutil", "matplotlib", "pandas")


def _which(name):
    """PATH first, then the known Windows install locations."""
    found = shutil.which(name)
    if found:
        return found, "PATH"
    if os.name == "nt":
        for d in WINDOWS_TOOL_DIRS:
            for ext in (".exe", ""):
                cand = os.path.join(d, name + ext)
                if os.path.isfile(cand):
                    return cand, "well-known-dir"
    return None, None


def _tool_version(path, name):
    """Return the first line of the tool's version banner, or None.

    bzip2 has no --version flag: it prints its banner to stderr and then waits on
    stdin, so it is fed an empty stdin and its stderr is what gets parsed.
    """
    try:
        proc = subprocess.run(
            [path, "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"version probe failed: {exc}"

    text = (proc.stdout or b"").decode("utf-8", errors="replace")
    err = (proc.stderr or b"").decode("utf-8", errors="replace")
    if name == "bzip2":
        text = err
    blob = text if text.strip() else err
    for line in blob.splitlines():
        line = line.strip()
        if line and not line.startswith("BZh"):
            return line, None
    return None, "version banner not parsed"


def _parse_xz_version(banner):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", banner or "")
    if not m:
        return None
    return tuple(int(g) for g in m.groups())


def detect_cpu():
    """CPU count, cgroup/affinity-aware.

    os.cpu_count() reports the host's core count inside a container, which on Kaggle
    over-reports what is actually schedulable. sched_getaffinity is the honest number
    where it exists (Linux only).
    """
    raw = os.cpu_count() or 1
    affinity = None
    if hasattr(os, "sched_getaffinity"):
        try:
            affinity = len(os.sched_getaffinity(0))
        except OSError:
            affinity = None

    if affinity is not None and affinity != raw:
        return {
            "count": affinity,
            "os_cpu_count": raw,
            "sched_getaffinity": affinity,
            "source": "sched_getaffinity",
            "note": (f"os.cpu_count()={raw} disagrees with affinity mask={affinity}; "
                     f"using {affinity} (cgroup/container limit)"),
        }
    return {
        "count": raw,
        "os_cpu_count": raw,
        "sched_getaffinity": affinity,
        "source": "sched_getaffinity" if affinity is not None else "os.cpu_count",
        "note": None,
    }


def detect_ram():
    try:
        import psutil
        vm = psutil.virtual_memory()
        return {
            "total_bytes": int(vm.total),
            "available_bytes": int(vm.available),
            "source": "psutil",
            "note": None,
        }
    except ImportError:
        pass

    if sys.platform.startswith("linux") and os.path.exists("/proc/meminfo"):
        info = {}
        with open("/proc/meminfo", "r") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                m = re.search(r"(\d+)", rest)
                if m:
                    info[key.strip()] = int(m.group(1)) * 1024
        if "MemTotal" in info:
            avail = info.get("MemAvailable", info.get("MemFree", info["MemTotal"] // 2))
            return {
                "total_bytes": info["MemTotal"],
                "available_bytes": avail,
                "source": "/proc/meminfo",
                "note": None,
            }

    return {
        "total_bytes": CONSERVATIVE_RAM_BYTES,
        "available_bytes": CONSERVATIVE_RAM_BYTES // 2,
        "source": "conservative-guess",
        "note": (f"psutil not installed and /proc/meminfo unavailable on "
                 f"{sys.platform}; ASSUMING {CONSERVATIVE_RAM_BYTES // 1024**3}GB total. "
                 f"All memory-derived sizing below is a GUESS -- install psutil to fix."),
    }


def detect_disk(path="."):
    target = os.path.abspath(path)
    while not os.path.exists(target):
        parent = os.path.dirname(target)
        if parent == target:
            break
        target = parent
    usage = shutil.disk_usage(target)
    return {
        "path": target,
        "total_bytes": usage.total,
        "free_bytes": usage.free,
        "source": "shutil.disk_usage",
    }


def detect_tools():
    out = {}
    for name in TOOLS:
        path, how = _which(name)
        if path is None:
            out[name] = {
                "available": False,
                "path": None,
                "version": None,
                "note": f"{name} not found on PATH or in any well-known install dir",
            }
            continue
        banner, verr = _tool_version(path, name)
        entry = {
            "available": True,
            "path": path,
            "found_via": how,
            "version": banner,
            "note": verr,
        }
        if name == "xz":
            parsed = _parse_xz_version(banner)
            entry["version_tuple"] = parsed
            if parsed is None:
                entry["supports_threading"] = False
                entry["note"] = ("could not parse xz version; assuming NO -T "
                                 "multithreading support")
            else:
                entry["supports_threading"] = parsed >= (5, 2, 0)
                if not entry["supports_threading"]:
                    entry["note"] = (f"xz {'.'.join(map(str, parsed))} < 5.2.0: "
                                     f"-T multithreading is NOT supported")
        out[name] = entry
    return out


def detect_py_libs():
    import importlib.util
    out = {}
    for name in PY_LIBS:
        spec = importlib.util.find_spec(name)
        entry = {"available": spec is not None, "version": None, "note": None}
        if spec is not None:
            try:
                mod = __import__(name)
                entry["version"] = getattr(mod, "__version__", None)
            except Exception as exc:
                entry["note"] = f"importable but failed to import: {exc}"
        out[name] = entry

    if not out["numpy"]["available"]:
        out["numpy"]["note"] = ("numpy MISSING -- the pure-Python LEB128 fallback is "
                                "50-100x slower and is strongly discouraged above the "
                                "64MB tier")
    if not out["tiktoken"]["available"]:
        out["tiktoken"]["note"] = "tiktoken MISSING -- hard requirement, nothing will run"
    if not out["zstandard"]["available"]:
        out["zstandard"]["note"] = ("zstandard MISSING -- zstd in_process_binding "
                                    "transport cells will be SKIPPED")
    if not out["psutil"]["available"]:
        out["psutil"]["note"] = ("psutil MISSING -- peak_rss_mb will be recorded as null "
                                 "rather than guessed")
    return out


def derive_defaults(cpu, ram, chunk_size):
    """Size the tokenization batch window from measured RAM, not a thread-count multiple.

    Peak transient memory for one batch is roughly, per chunk:
      chunk_size (raw bytes)
      + ~2x chunk_size (the Python str after decode; CPython stores latin-1 prose
        compactly but the decode still allocates)
      + 4 bytes per token, at ~0.26 tokens/byte for o200k on English prose
      + the packed output, ~0.55x chunk_size for LEB128
    which totals ~4.6x chunk_size. Rounded to 5x for headroom, held to 25% of
    available RAM (handoff Section 6).

    The upper clamp of 128 is a judgment call the handoff does not make: past roughly
    4x the thread count the batch no longer improves thread saturation and only raises
    peak RSS, so on a large-RAM machine the RAM formula alone would pick a batch that
    holds ~1GB of text at once for no throughput gain. The clamp also keeps the
    0.5x/2x axis values (Section 5.1) in a range that is meaningful to compare.
    """
    per_chunk = int(chunk_size * 5)
    budget = int(ram["available_bytes"] * 0.25)
    raw = budget // per_chunk
    batch = min(max(4, raw), 128)
    return {
        "threads_default": cpu["count"],
        "batch_chunks_default": batch,
        "batch_chunks_derivation": (
            f"floor(0.25 * {ram['available_bytes'] / 1024**3:.2f}GiB available / "
            f"(5 * {chunk_size / 1024**2:.0f}MiB per chunk)) = {raw}, "
            f"clamped to [4, 128] -> {batch}"),
    }


def detect(path=".", chunk_size=2 * 1024 * 1024):
    cpu = detect_cpu()
    ram = detect_ram()
    disk = detect_disk(path)
    return {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "sys_platform": sys.platform,
        },
        "cpu": cpu,
        "ram": ram,
        "disk": disk,
        "tools": detect_tools(),
        "py_libs": detect_py_libs(),
        "derived": derive_defaults(cpu, ram, chunk_size),
    }


def max_feasible_tier(info, tier_bytes, multiplier=3.5):
    """handoff 4.2: require ~3.5x the corpus size in free disk."""
    need = int(tier_bytes * multiplier)
    return info["disk"]["free_bytes"] >= need, need


def _gb(n):
    return f"{n / 1024 ** 3:.2f} GiB"


def print_report(info, stream=sys.stdout):
    p = lambda *a: print(*a, file=stream)
    p("=" * 74)
    p("parmar resource detection")
    p("=" * 74)
    pl = info["platform"]
    p(f"platform            {pl['system']} {pl['release']} ({pl['machine']}), "
      f"Python {pl['python']}")

    cpu = info["cpu"]
    p(f"cpu count           {cpu['count']}  [source: {cpu['source']}]")
    if cpu["note"]:
        p(f"  ! {cpu['note']}")

    ram = info["ram"]
    p(f"ram                 {_gb(ram['total_bytes'])} total, "
      f"{_gb(ram['available_bytes'])} available  [source: {ram['source']}]")
    if ram["note"]:
        p(f"  ! {ram['note']}")

    disk = info["disk"]
    p(f"disk ({disk['path']})")
    p(f"                    {_gb(disk['free_bytes'])} free of {_gb(disk['total_bytes'])}")

    p("cli tools")
    for name, t in info["tools"].items():
        if t["available"]:
            extra = ""
            if name == "xz":
                extra = f"  [-T threading: {'yes' if t.get('supports_threading') else 'NO'}]"
            p(f"  {name:<8} OK   {t['version']}{extra}")
            p(f"           {' ' * 4} {t['path']}  (via {t.get('found_via')})")
        else:
            p(f"  {name:<8} MISSING")
        if t.get("note"):
            p(f"  {' ' * 8} ! {t['note']}")

    p("python libs")
    for name, lib in info["py_libs"].items():
        state = f"OK   {lib['version']}" if lib["available"] else "MISSING"
        p(f"  {name:<12} {state}")
        if lib.get("note"):
            p(f"  {' ' * 12} ! {lib['note']}")

    d = info["derived"]
    p("derived defaults")
    p(f"  threads_default      {d['threads_default']}")
    p(f"  batch_chunks_default {d['batch_chunks_default']}")
    p(f"    derivation: {d['batch_chunks_derivation']}")

    p("corpus tier feasibility (needs 3.5x tier size free on disk)")
    for label, size in (("64MB", 64 * 1024 ** 2), ("256MB", 256 * 1024 ** 2),
                        ("1GB", 1024 ** 3), ("4GB", 4 * 1024 ** 3),
                        ("8GB", 8 * 1024 ** 3)):
        ok, need = max_feasible_tier(info, size)
        p(f"  {label:<6} {'FEASIBLE' if ok else 'NOT FEASIBLE'}  (needs {_gb(need)})")
    p("=" * 74)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="parmar resource detection (handoff Section 6)")
    ap.add_argument("--path", default=".", help="path whose filesystem to measure")
    ap.add_argument("--json", action="store_true", help="emit raw JSON instead of a report")
    args = ap.parse_args()
    info = detect(args.path)
    if args.json:
        print(json.dumps(info, indent=2, default=str))
    else:
        print_report(info)


if __name__ == "__main__":
    main()
