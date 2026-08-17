#!/usr/bin/env python3
"""Keep the language-invariant parts of every translation in sync with the English README.

A 550-line technical document copied into eight languages drifts the moment the
English one changes -- and it already did, twice, while the header was being
iterated on. The prose has to be maintained by hand (ideally by someone who speaks
the language), but the parts that are identical in every file should not be:

  * the ASCII title block
  * the badge row, with paths rewritten to ../../
  * the language navigation bar, with the current language bolded and unlinked
  * the image paths inside the figure <picture> blocks, rewritten to ../../

This rewrites exactly those, in place, in every docs/i18n/README.*.md. Prose is
never touched -- note in particular that figure *alt* text is translated, so the
<picture> blocks are path-corrected rather than copied wholesale.

    python docs/i18n/sync_boilerplate.py [--check]

--check exits non-zero if anything is out of sync, for use in CI.
"""

import argparse
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent

# display name -> filename stem; order is the order shown in the nav bar
LANGS = [
    ("English", None),
    ("简体中文", "zh-CN"),
    ("Español", "es"),
    ("Português", "pt-BR"),
    ("Русский", "ru"),
    ("日本語", "ja"),
    ("Deutsch", "de"),
    ("Français", "fr"),
    ("한국어", "ko"),
]


def english():
    return (ROOT / "README.md").read_text(encoding="utf-8")


def block(src, pattern, what):
    m = re.search(pattern, src, re.S)
    if not m:
        sys.exit(f"could not find the {what} in README.md -- "
                 f"sync_boilerplate.py needs updating")
    return m.group(0)


def nav_for(stem):
    parts = []
    for name, s in LANGS:
        if s == stem:
            parts.append(f"  <b>{name}</b>")
        elif s is None:
            parts.append(f'  <a href="../../README.md">{name}</a>')
        else:
            parts.append(f'  <a href="README.{s}.md">{name}</a>')
    return '<p align="center">\n' + " ·\n".join(parts) + "\n</p>"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    src = english()
    header = block(src, r'<div align="center">\n\n<pre>\n.*?\n</div>', "header block")
    # translations sit two directories down, so every repo-relative link shifts
    header_rel = re.sub(r'(href|srcset|src)="(?!https?:|\.\./)', r'\1="../../', header)
    # the DOCS badge already points at an absolute URL and must not be rewritten
    figures = set(re.findall(r'(?:srcset|src)="report/([a-z_]+\.png)"', src))

    stale = []
    for name, stem in LANGS:
        if stem is None:
            continue
        p = HERE / f"README.{stem}.md"
        if not p.exists():
            print(f"  -- README.{stem}.md missing (nav will still link to it)")
            continue
        before = p.read_text(encoding="utf-8")
        after = before

        after = re.sub(r'<div align="center">\n\n<pre>\n.*?\n</div>',
                       header_rel.replace("\\", "\\\\"), after, count=1, flags=re.S)
        after = re.sub(r'<p align="center">.*?</p>', nav_for(stem).replace("\\", "\\\\"),
                       after, count=1, flags=re.S)

        # figure alt text is translated, so only the paths are corrected here
        after = re.sub(r'((?:srcset|src)=")report/', r'\1../../report/', after)
        missing = figures - set(re.findall(r'(?:srcset|src)="\.\./\.\./report/([a-z_]+\.png)"',
                                           after))
        if missing:
            print(f"  !! {p.name} is missing figures: {', '.join(sorted(missing))}")

        if after != before:
            stale.append(p.name)
            if not args.check:
                p.write_text(after, encoding="utf-8", newline="\n")
                print(f"  synced {p.name}")
        else:
            print(f"  ok     {p.name}")

    if args.check and stale:
        print(f"\nout of sync: {', '.join(stale)}")
        print("run: python docs/i18n/sync_boilerplate.py")
        return 1
    if not args.check:
        print(f"\n{len(stale)} file(s) updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
