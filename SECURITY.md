# Security Policy

## What parmar is, in security terms

parmar is an offline research harness for compression experiments. It is **not** a
hardened archival format and should not be treated as one. Specifically:

* The archive format has no authentication and no encryption. The sha256 in the
  footer is an **integrity check against accidental corruption**, not a MAC — it is
  stored in the clear next to the data it describes, so anyone who can modify the
  payload can modify the hash to match.
* Decompression allocates memory driven by values read from the archive (token
  batches, and for `zstd_22_long` a window of up to 2 GiB). A hostile archive can
  make it allocate more than you want.
* `parmar_core` shells out to `xz`, `zstd`, `gzip` and `bzip2`. Argument vectors are
  built from a fixed internal table and never from archive contents, and every
  subprocess is launched as an argv list — never through a shell — so archive data
  cannot inject arguments. Tool *paths* come from `PATH` or from a fixed list of
  well-known install directories, so a writable directory earlier on `PATH` is the
  usual caveat.

**Do not decompress parmar archives from untrusted sources**, and do not use this
format for anything where authenticity matters. If you need that, wrap it in
something that provides it.

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue:

* Use GitHub's **[Report a vulnerability](https://github.com/shallowbyte/parmar/security/advisories/new)**
  (Security → Advisories), or
* email **ronakparmar2428@gmail.com**

Please include the version or commit, your platform and tool versions
(`python resources.py` prints all of them), and a minimal reproduction. A crash or
an unbounded allocation reachable from a crafted archive is in scope.

Expect an acknowledgement within about a week. This is a personal research project,
not a funded product, so there is no formal SLA — but reports will be taken
seriously and credited unless you prefer otherwise.

## Out of scope

* The absence of authenticated encryption in the archive format (documented above,
  by design).
* Resource exhaustion from an archive you chose to decompress after being told not
  to trust it.
* Vulnerabilities in `xz`, `zstd`, `gzip`, `bzip2`, `tiktoken`, or `numpy` — please
  report those upstream. (If parmar *invokes* one of them in an unsafe way, that
  part is in scope.)
