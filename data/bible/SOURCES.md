# Keyword Index — Source Documentation

Per-verse keyword enrichment for FTS search: topical keywords (Nave's) +
lemma/gloss keywords (Strong's). Built offline by `build_keywords.py` into
`data/indexes/keywords.pkl`. This document exists so the future installation
manager can fetch, verify, and attribute each resource.

## Resources

### 1. Nave's Topical Bible (subjects → verse references)

- **What:** 5,319 topical subjects, each with subtopics and abbreviated
  verse references (e.g. subject `AARON`, entry `-Makes the golden calf
  EXO 32; ACT 7:40; DEU 9:20,21`). Inverted at build time into
  verse → keyword sets (subject + subtopic words become index terms).
- **Upstream content:** Orville J. Nave, 1897 — public domain in the US.
- **Machine-readable compilation:** `NavesTopicalDictionary.csv` from
  BradyStephenson/bible-data
  (`https://github.com/BradyStephenson/bible-data`).
- **Download URL (pinned):**
  `https://raw.githubusercontent.com/BradyStephenson/bible-data/main/NavesTopicalDictionary.csv`
- **License of the compilation:** CC BY 4.0 (attribution required even
  though the underlying text is public domain).
- **Credit line (ship in installer / about screen):**
  "Topical data from Nave's Topical Bible (public domain, 1897), via the
  BradyStephenson/bible-data compilation, licensed CC BY 4.0."
- **Format:** CSV, UTF-8 with BOM; columns `section,subject,entry`.
  References use 2–4 letter book abbreviations (`EXO`, `1CH`, `PSA`,
  variants `JHN`/`JOHN`, `1JHN`/`1JN`), with `;`-separated segments,
  comma lists (`6:2,3`), ranges (`6:16-20`), chapter-only refs (`EXO 28`),
  and carry-forward context (`1CH 6:3-15,50-53; 24`).
- **Fetched:** 2026-09-29, 1,461,993 bytes.

### 2. KJV interlinear tagging (verse → Strong's numbers)

- **What:** Word-by-word tagging for 31,102 verses: each word carries its
  Strong's number (`G26`, `H2617`) plus a short English definition.
  Gives every verse its lemma identity (`agape` even where KJV says
  "charity").
- **File:** `kjvstudy_org/data/interlinear.json.gz` from
  kennethreitz/kjvstudy.org (`https://github.com/kennethreitz/kjvstudy.org`).
- **Download URL (pinned):**
  `https://raw.githubusercontent.com/kennethreitz/kjvstudy.org/main/kjvstudy_org/data/interlinear.json.gz`
- **License:** ISC (per repository LICENSE; underlying tagging derived
  from public-domain Strong's-aligned sources).
- **Format:** gzipped JSON; keys `"Book:chapter:verse"` (e.g.
  `"Acts:1:1"`), values are word lists with `position, original,
  transliteration, strongs, english, parsing, definition`.
- **Fetched:** 2026-09-29, 12,451,543 bytes.

### 3. Strong's lexicon (number → English gloss)

- **What:** 8,674 Hebrew + 5,523 Greek entries mapping each Strong's
  number to lemma, transliteration, and short KJV gloss (`kjv_def`).
  The gloss words become the per-verse keyword terms.
- **Files:** `kjvstudy_org/data/strongs/hebrew.json`,
  `kjvstudy_org/data/strongs/greek.json` (same repo as above).
- **Download URLs (pinned):**
  `https://raw.githubusercontent.com/kennethreitz/kjvstudy.org/main/kjvstudy_org/data/strongs/hebrew.json`
  `https://raw.githubusercontent.com/kennethreitz/kjvstudy.org/main/kjvstudy_org/data/strongs/greek.json`
- **License:** ISC (repository); underlying Strong's Exhaustive
  Concordance (1890) is public domain.
- **Format:** JSON objects keyed `H1..H8674` / `G1..G5624` with
  `lemma, xlit/translit, pron, derivation, strongs_def, kjv_def`.
- **Fetched:** 2026-09-29, hebrew 2,002,360 bytes, greek 1,199,841 bytes.

## Installer notes

1. All three downloads are small (~17 MB total) and static; pin the URLs
   above and verify byte sizes after fetch (record actual SHA-256 in the
   install manifest at pack time — SHAs live in `keywords_meta.json`
   after each build).
2. Sources are NOT committed to git (see `.gitignore`: `data/bible/sources/`);
   `build_keywords.py --fetch` re-downloads them.
3. Attribution: the Nave's credit line above must be displayed anywhere
   the keyword index ships (installer screen and/or app About). The
   Strong's content is public domain / ISC — credit appreciated, not required.
4. No copyrighted Bible translation text is involved: keywords are topics,
   lemma names, and short glosses. Verse *text* shown for keyword hits is
   looked up live from `bible.db` in the operator's chosen display
   translation (`search.keyword_display_translation` setting).
5. Rebuild trigger: re-run `build_keywords.py` if `bible.db` verse
   coordinates change (new/removed verses invalidate reference validation).

## Build outputs (`data/indexes/`)

- `keywords.pkl` — numpy postings compact in the exact `core/bible_service`
  `_load_postings` format (postings/idf/avgdl/doc_len/k1/b/corpus_size/
  lookup…), keyed per KJV verse coordinate; scored at query time with the
  shared `_score_postings` (bit-identical BM25 arithmetic, own idf mass).
- `keywords_meta.json` — verse coverage (Nave's/Strong's/both/neither),
  term counts, source SHAs, build timestamp.
- `keywords_fingerprint.json` — input SHAs for rebuild-change detection.
