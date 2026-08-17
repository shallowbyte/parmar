# `docs/i18n/` — translations

Translations of the top-level [`README.md`](../../README.md), provided so the results
are readable without English. One file per language:

| language | file |
|---|---|
| 简体中文 (Simplified Chinese) | [`README.zh-CN.md`](README.zh-CN.md) |
| Español (Spanish) | [`README.es.md`](README.es.md) |
| Português do Brasil | [`README.pt-BR.md`](README.pt-BR.md) |
| Русский (Russian) | [`README.ru.md`](README.ru.md) |
| 日本語 (Japanese) | [`README.ja.md`](README.ja.md) |
| Deutsch (German) | [`README.de.md`](README.de.md) |
| Français (French) | [`README.fr.md`](README.fr.md) |
| 한국어 (Korean) | [`README.ko.md`](README.ko.md) |

## The English README is normative

Where a translation and the English README disagree, **the English one is correct.**
This matters more than usual here: the repository's whole point is a set of measured
claims, several of them counter-intuitive and easy to soften or invert in translation
("plateaus" is not "stops", "smaller *and* faster" is not "smaller *or* faster"). The
translations are an accessibility layer, not a second source of truth.

If you read one of these and something seems wrong, check the English text before
filing an issue — and if the English text is what's wrong, that is a much more
interesting bug.

## What is deliberately left untranslated

* code blocks, shell commands and flags
* file names, function names and identifiers (`read_chunks`, `fixed_u16`, `lzma_fast`)
* backend and tokenizer names
* every number, ratio and measurement
* the mermaid diagrams, whose labels are almost entirely code identifiers

This is the usual convention for technical documentation, and it keeps the parts a
reader will copy-paste byte-identical to the English source.

## Keeping them current

Each translation carries the commit it was translated from, at the bottom of the file.
Full duplicates of a 500-line document drift the moment the English one changes, so
treat a stale marker as "read the English version for anything load-bearing" rather
than as a promise the numbers are current.

When you change the English README:

1. If you changed **prose**, the translations are stale. Update them, or update the
   marker so readers know.
2. If you changed **numbers**, update every translation — a wrong number is worse than
   an untranslated one.
3. If you only changed the header, badges or ASCII art, those blocks are duplicated
   verbatim across all files and can be patched mechanically.

Contributions from native speakers are very welcome, especially corrections to the
technical vocabulary — the translations were produced by a single non-specialist pass
and the compression terminology in particular deserves a second pair of eyes.
