# LawCodex — Norway (Norge)

Norwegian legislation in force — Grunnloven, all laws (*lover*) and all central regulations
(*sentrale forskrifter*) — as consolidated Markdown, one file per document. The texts are in
Norwegian (bokmål or nynorsk, as Lovdata publishes them).

Part of [LawCodex](https://github.com/LawCodex): the legislation of every country, as plain
Markdown in git.

## Coverage

Snapshot of Lovdata's public datasets as of **2026-10-10** (retrieved 2026-10-11).

| Directory | Lovdata base | Content | Files |
|---|---|---|---:|
| `grunnloven/` | NL | Kongeriket Norges Grunnlov (bokmål `grunnloven.md` and nynorsk `grunnloven-nynorsk.md`) | 2 |
| `lover/<year>/` | NL | Laws in force (*gjeldende lover*), consolidated | 753 |
| `forskrifter/<year>/` | SF | Central regulations in force (*sentrale forskrifter*), consolidated | 3,430 |
| `delegeringsvedtak/<year>/` | DEL | Delegation decisions (*delegeringsvedtak*) | 1,427 |
| `instrukser/<year>/` | INS | Instructions (*instrukser*) | 185 |
| `stortingsvedtak/<year>/` | STV | Plenary decisions of the Storting (e.g. tax and duty resolutions, Storting rules) | 84 |
| | | **Total** | **5,881** |

`lover/` also contains the amending acts (*endringslover*) that Lovdata still lists among the laws
in force (typically because part of them has not yet entered into force).

### Not covered

- **Local regulations** (*lokale forskrifter*, LF) — not part of Lovdata's free public data.
- **Repealed** laws and regulations, and historical (point-in-time) versions.
- *Norsk Lovtidend* (the official gazette, as-enacted texts) — available from the same API
  (`lovtidend-avd1-*.tar.bz2`) but not converted here.
- Court decisions, preparatory works, treaties (other than those embedded in laws), EEA acts.
- Images are not stored in the repo; `![...]()` links point to `https://lovdata.no/static/...`.
- Lovdata's hyperlinks between documents are reduced to their link text.

## Source and licence

- Source: [Lovdata](https://lovdata.no/) public API, free bulk datasets
  <https://api.lovdata.no/v1/publicData/list>:
  `gjeldende-lover.tar.bz2` (laws in force) and `gjeldende-sentrale-forskrifter.tar.bz2`
  (central regulations in force), each an archive of HTML/XML documents, one per law/regulation.
- Licence: the datasets are published under the
  [Norsk lisens for offentlige data (NLOD) 2.0](https://data.norge.no/nlod/no/2.0)
  (attribution: *"Inneholder data under Norsk lisens for offentlige data (NLOD) distribuert av
  Lovdata"*). Laws and regulations are moreover not subject to copyright in Norway
  (åndsverkloven § 14). The Markdown conversion in this repository is offered under the same terms.
- This is **not** an official publication. The authoritative texts are those published by
  Lovdata / Norsk Lovtidend.

## File format

```
lover/2005/2005-05-20-28-straffeloven.md
forskrifter/2017/2017-07-25-1215-forskrift-om-ny-mat.md
```

File names are `<date>-<number>-<slug>.md`, where `<date>-<number>` is the Lovdata identifier
(`LOV-2005-05-20-28`, `FOR-2017-07-25-1215`) and the slug is derived from the short title
(æ→ae, ø→o, å→a). Directories are sharded by year of enactment (all < 1,000 entries).

Each file starts with YAML front matter:

```yaml
title: "Lov om straff (straffeloven)"
short_title: "Straffeloven – strl."
identifier: "LOV-2005-05-20-28"     # Lovdata ID (LOV-/FOR-yyyy-mm-dd-nr)
type: act                            # constitution | act | regulation | delegation | instruction | parliamentary_decision
jurisdiction: "no"
language: "nb"                       # as declared by Lovdata: nb (bokmål), nn (nynorsk), no (unspecified)
date: 2005-05-20                     # date of the act/regulation
in_force_from: 2015-10-01            # Lovdata "Ikrafttredelse" (may be text, e.g. "Kongen bestemmer")
last_amended: 2026-07-01             # entry into force of the latest consolidated amendment
last_amended_by: "..."
ministry: "Justis- og beredskapsdepartementet"
status: in_force                     # in_force | not_yet_in_force | unknown ("Kongen bestemmer")
source: "https://lovdata.no/dokument/NL/lov/2005-05-20-28"
retrieved: 2026-10-11
licence: "NLOD 2.0 (Norsk lisens for offentlige data)"
```

The body keeps the document's structure: parts/chapters (*del*, *kapittel*) and sections (§) as
headings at the level Lovdata uses; lettered/numbered items as lists (labels preserved);
Lovdata's amendment notes (*Endret ved ...*) as italic paragraphs; the "Annet om dokumentet"
note as a block quote under the title; footnotes as Markdown footnotes; simple tables as Markdown
tables, tables with merged cells as HTML; formulas as LaTeX (`$$ ... $$`).

## Regenerating

```sh
python3 -m pip install -r scripts/requirements.txt
python3 scripts/fetch.py ../_raw/no                       # downloads + extracts to ../_raw/no/ex
python3 scripts/convert.py ../_raw/no/ex . --retrieved $(date +%F)
```

`convert.py` overwrites files in place; delete the content directories first to drop documents
that have been repealed since the previous run.
