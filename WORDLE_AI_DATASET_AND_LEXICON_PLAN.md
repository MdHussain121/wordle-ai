# WORDLE_AI_DATASET_AND_LEXICON_PLAN.md

**Status:** Phase 0 deliverable, revision 1.0 · **Date:** 2026-11-19
**Measurement basis:** `tools/measure_lexicons.py` → `data/processed/measurements.json` (exit 0)
**Related:** `WORDLE_AI_RESEARCH_REPORT.md` §11 and Appendix A; risk register R-01…R-04

All counts marked `[R]` in this document were measured on 2026-11-19 from the files listed in
§2. Nothing here is estimated except where marked `[E]` or `[U]`.

---

## 1. Purpose and principles

The lexicon is the single largest source of correctness risk in this project. Two different
games can share a name and differ entirely in behaviour because their word lists differ. The
design therefore treats a word list as **data with provenance**, never as a constant:

1. **Guess set and answer set are separate objects.** `answers ⊆ guesses` is enforced. A profile
   may legitimately have a much larger guess set than answer set (classic: 12,972 vs 2,315).
2. **No silent substitution.** If a profile's files are missing, the loader fails; it does not
   fall back to a similar list.
3. **Every profile is identified by content, not by name.** The manifest checksum, not
   `"strict"`, is the identity used by caches, policies and benchmark records.
4. **The build is reproducible from pinned inputs.** Source versions and SHA-256 checksums are
   recorded; the pipeline is deterministic; two builds of the same inputs are byte-identical.
5. **Policy is configurable and explicit.** Whether possessives, proper nouns, archaic words,
   dialect spellings or one-letter entries are included is a documented rule per profile, with a
   count of what it excluded.
6. **Never redistribute what you cannot license.** The classic Wordle lists are user-supplied
   and never bundled.

---

## 2. Source inventory (as evaluated and measured)

| Source | Version / retrieval | Licence | Redistribution | Role |
|---|---|---|---|---|
| **SCOWL** (Spell Checker Oriented Word Lists) | 2020.12.07, `scowl-2020.12.07.zip`, SHA-256 `dc3435e1cb56f3394aea91b5d2ab5d10d80c98bc7dd88c3fccb7348f6ab913a0` `[R]` | Permissive, MIT/X11-style, notice required; commercial use allowed | Yes, with copyright + permission notice | Primary open lexicon, size and dialect control |
| **ENABLE 2K** master word list | `enable1.txt`, SHA-256 `3f16130220645692ed49c7134e24a18504c2ca55b3c012f7290e3e77c63b1a89` `[R]` | Public domain | Yes, unrestricted | Broad coverage, especially shorter lengths and modern words |
| **12Dicts** | Bundled inside SCOWL composition | Public domain | Yes | Transitively included via SCOWL; not used directly |
| **Princeton WordNet 3.0** | 3.0 | Princeton WordNet licence (permissive, commercial allowed) | Yes, with notice | Lexical metadata (POS, lemma validity checks); optional |
| **Open English WordNet** | current release | CC BY 4.0, derived from Princeton WordNet under the WordNet licence (verified in `LICENSE.md`) | Yes, with attribution to both Princeton WordNet and the OEWN team | Optional future metadata source; not required for v1 |
| **wordfreq** | 3.1.x | Apache-2.0 **code**, **CC BY-SA 4.0 data** | Data redistribution constrained; README refuses CSV-style extraction | Optional runtime frequency prior; values are computed at runtime, never bundled |
| **Classic Wordle answer/guess lists** | 2,315 / 12,972, retrieved as user-supplied research input `[R]` | No clear open licence | **No** | Only for the `classic` profile, supplied by the user |
| **UKACD, YAWL** | referenced inside SCOWL's composition notes | Not independently evaluated | Not used | Excluded to avoid unattributed obligations |
| **Corpus of Contemporary American English (COCA)** | 3-gram data, not redistributable | Used by SCOWL under NDA | Not redistributed | Affects SCOWL's size classification only; not used directly |

### 2.1 Obligations that follow

- Ship a `THIRD_PARTY_NOTICES.md` reproducing the SCOWL copyright and permission notice in full,
  the ENABLE public-domain statement with credit to its maintainers, the WordNet notice if
  WordNet metadata is used, and the wordfreq attribution if the optional prior is installed.
- Do **not** commit `data/raw/` or `data/user/`. `.gitignore` must contain both.
- Do **not** publish derived frequency tables from wordfreq. Compute Zipf scores at runtime from
  the installed package.
- If a future distribution includes built lexicons, include the notices and a manifest that names
  every source, because a built lexicon is a derived work of its inputs.

---

## 3. Composition rules discovered by measurement

These are not style preferences; each one silently corrupts a naive build.

### 3.1 SCOWL size files are incremental

`final/<category>-words.<size>` contains only the entries introduced at that size level. A
dictionary of "size 80" is the union of levels 10, 20, 35, 40, 50, 55, 60, 70, 80. Measured
incremental English counts `[R]`:

| Level | 10 | 20 | 35 | 40 | 50 | 55 | 60 | 70 | 80 | 95 |
|---|---|---|---|---|---|---|---|---|---|---|
| Entries | 4,373 | 7,951 | 36,103 | 6,391 | 23,796 | 6,233 | 13,438 | 33,270 | 139,207 | 219,479 |

Cumulative totals are far larger than any single file: English+American reaches 49,704 at size
35 and 502,141 at size 95 `[R]`.

### 3.2 `english-words` is the neutral base list, not "all English"

SCOWL stores exactly one spelling per word in the neutral list. `color` lives in
`american-words.10`; `colour` lives in `british-words.10`; neither is in `english-words`. SCOWL's
own README instructs that a usable dictionary is `english` **plus one dialect category**.

Measured, all levels, ASCII-alpha only `[R]`:

| Composition | Total | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|---|
| english only | 490,233 | 26 | 251 | 1,929 | 7,301 | 17,818 |
| english + american | 502,141 | 26 | 260 | 1,949 | 7,389 | 17,994 |
| english + british | 502,206 | 26 | 251 | 1,943 | 7,352 | 17,952 |

American and British differ by a **symmetric difference of 23,753** entries `[R]`. Dialect is
therefore part of the profile identity, and the default is `american` because the reference game
is American English.

### 3.3 SCOWL is ISO-8859-1

Reading `final/*` as UTF-8 raises `UnicodeDecodeError` (observed at byte 2711 during this spike).
The loader decodes UTF-8 first and falls back to Latin-1, recording each fallback in the
manifest. Under the broad open union, **948 entries contain non-ASCII characters** `[R]`; they
are excluded by the English policy and counted.

### 3.4 Possessives dominate the rejected mass

Of 507,556 raw entries in the broad open union, **76,390 contain an apostrophe** (almost all
possessives such as `aardvark's`), and the ASCII-alpha rule rejects 77,082 in total `[R]`. A
build that forgets this ships a 5-letter list polluted by four-letter stems and inflates every
length bucket.

### 3.5 Single letters

SCOWL includes all 26 letters as entries at size ≥ 40; ENABLE includes none. English has exactly
two one-letter words: `a` and `i`. The L=1 profile therefore requires an explicit inclusion
rule (`{"a", "i"}`), not a length filter. The other 24 entries are letter *names*, not words, and
must be excluded with a recorded reason.

### 3.6 The classic lists are not reproducible from open sources

Measured coverage of the classic game vocabulary `[R]`:

| Source | Answers covered | Allowed guesses covered |
|---|---|---|
| SCOWL ≤35 American | 1,914 / 2,315 (82.68%) | 3,461 / 12,972 (26.68%) |
| SCOWL ≤50 American | 2,205 / 2,315 (95.25%) | 4,440 / 12,972 (34.23%) |
| SCOWL ≤60 American | 2,255 / 2,315 (97.41%) | 5,054 / 12,972 (38.96%) |
| SCOWL ≤70 American | 2,277 / 2,315 (98.36%) | 6,405 / 12,972 (49.38%) |
| SCOWL ≤80 American | 2,282 / 2,315 (98.57%) | 10,901 / 12,972 (84.03%) |
| ENABLE | 2,306 / 2,315 (99.61%) | 8,635 / 12,972 (66.57%) |
| SCOWL ≤80 ∪ ENABLE | 2,313 / 2,315 (99.91%) | 11,223 / 12,972 (86.52%) |
| Full open (SCOWL ≤95 ∪ ENABLE) | 2,313 / 2,315 (99.91%) | 12,159 / 12,972 (93.73%) |

The two absent answers are `admin` and `cyber`. Nine answers are absent from ENABLE alone:
`abled, admin, bicep, cyber, email, inbox, login, manga, ramen`. **Conclusion:** the classic
profile must be user-supplied. Substituting an open list changes the valid guess space by up to
1,777 words, which changes the optimal opener and invalidates published comparisons.

### 3.7 Version churn in the reference game

| Configuration | Answers | Allowed guesses | Optimal opener / average |
|---|---|---|---|
| Original (2021) | 2,315 | 12,972 | `salet` / 3.4212 `[P]` |
| NYT 2022-02-15 | 2,309 | 12,947 | `salet` / 3.4201 `[P]` |
| NYT 2022-08-30 | 2,309 | 14,855 | `tarse` / 3.4140 (7,883/2,309) `[P]` |
| NYT 2023-07-01 | 3,158 | 14,855 | `tarse` / 3.5526 `[P]` |

**Source discrepancy, recorded rather than resolved silently.** Greenberg's 2024 table lists the
2023 configuration as 14,885 allowed guesses, while the wordle-opt reproduction publishes 14,855
(the number used here, matching the list file it ships and reproduces on 16 cores). The two figures
appear in print; this corpus uses 14,855 and any future profile import records the guessed-list
checksum so the difference cannot matter silently.

Each row is a distinct profile with a distinct checksum. The system ships none of them; it ships
the *profiles* and a loader that requires the user to supply matching files. This is the only
defensible response to lists that change without notice and carry no open licence.

---

## 4. Validity policy

Every rule below is a configuration key with an explicit default, and every build reports the
count it removed. The English defaults implement "a word you could reasonably be expected to
type in a game of Wordle".

### 4.1 Character and normalisation policy

```
accept_char_class   = "[a-z]"          # for English profiles
normalization       = NFC              # applied before casefold
case_handling       = casefold         # "Apple" -> "apple"
length_metric       = grapheme_clusters
silent_transliteration = false         # never strip accents to force a word into the alphabet
```

Consequences, stated explicitly because each is a place a naive pipeline corrupts input:

- `café` is **rejected** for English L=4, not converted to `cafe`. Transliteration is a separate,
  opt-in transform that must be recorded in the manifest, because it changes the word's identity.
- A combining-mark sequence such as `e` + U+0301 normalises to `é` and is then measured as
  length 1, not 2.
- Emoji and other multi-code-point graphemes are measured as one user-perceived character. They
  are rejected by the English alphabet rule, but the *length* they report is the honest one, so a
  future non-Latin profile is not broken by code-point counting.
- Uppercase is folded, not dropped; proper nouns are excluded by the policy rule in §4.2, not by
  a case heuristic.

### 4.2 Inclusion rules

| Category | Default | Rationale | Configurable |
|---|---|---|---|
| Lowercase alphabetic words | include | core vocabulary | `rules.include_lowercase` |
| Proper nouns | exclude | SCOWL isolates them in `*-proper-names.*`; Wordle rejects them | `rules.include_proper_nouns` |
| Abbreviations/acronyms | exclude | `*-abbreviations.*`; not words in the game sense | `rules.include_abbreviations` |
| Uppercase entries | exclude | casing, not vocabulary | `rules.include_uppercase` |
| Possessives (`word's`) | exclude | 76,390 entries `[R]`; not standalone words | `rules.include_possessives` |
| Hyphenated compounds | exclude | not playable as single tokens | `rules.include_hyphenated` |
| Spaces, digits, punctuation | exclude | not playable | not configurable |
| Inflected forms (plurals, past tense) | include if the source lists them | they are valid guesses and often valid answers; the source, not a stemmer, decides | `rules.include_inflections` |
| Archaic/rare | include in `extended`/`full`, exclude in `strict` | governed by SCOWL size thresholds | profile-level |
| Slang / informal | include only if present in ENABLE or SCOWL ≤80 | no separate slang list is bundled | `rules.include_slang` |
| Regional spellings | per dialect (`american` default, `british` selectable) | 23,753-entry difference `[R]` | `profile.dialect` |
| Single letters | `{a, i}` only | English has two; SCOWL lists 26 letter names `[R]` | `rules.single_letter_whitelist` |
| Non-ASCII | exclude in English | 948 entries `[R]`; never transliterate silently | `rules.ascii_only` |

### 4.3 Answer-set policy (separate from validity)

Being a valid guess does not make a word a plausible secret. The answer policy is stricter and
profile-specific:

- `strict`: common vocabulary only (SCOWL ≤50, American composition).
- `extended`: broad vocabulary (SCOWL ≤80 ∪ ENABLE).
- `full`: everything the validity policy accepts (SCOWL ≤95 ∪ ENABLE).
- `classic`: exactly the user-supplied list.
- `custom`: exactly the user's file, with `answers ⊆ guesses` enforced.

The default answer policy is `strict`, because a solver benchmarked against archaic answers
overstates the value of obscure guesses. Benchmark records always state the answer policy.

### 4.4 Measured profile sizes `[R]`

ASCII-alpha, per length:

| Profile | Definition | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|---|
| `strict.en.L` | SCOWL ≤50, english+american | 26 → policy `{a,i}` | 65 | 588 | 2,303 | **4,444** |
| `extended.en.L` | SCOWL ≤80 ∪ ENABLE | 26 → `{a,i}` | 148 | 1,223 | 5,059 | **11,411** |
| `full.en.L` | SCOWL ≤95 ∪ ENABLE | 26 → `{a,i}` | 276 | 2,000 | 7,441 | **17,410** |
| `classic.en.5` | user-supplied | — | — | — | — | **2,315 / 12,972** |

SCOWL size ladder for reference (American composition, all lengths) `[R]`:

| Size | Total | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|---|
| 35 | 49,704 | 2 | 43 | 482 | 1,898 | 3,838 |
| 40 | 56,324 | 26 | 57 | 504 | 2,015 | 4,086 |
| 50 | 80,919 | 26 | 65 | 589 | 2,335 | 4,918 |
| 55 | 87,379 | 26 | 68 | 641 | 2,484 | 5,233 |
| 60 | 101,367 | 26 | 73 | 663 | 2,611 | 5,569 |
| 70 | 135,951 | 26 | 97 | 796 | 3,211 | 6,935 |
| 80 | 279,729 | 26 | 131 | 1,146 | 5,003 | 11,724 |
| 95 | 502,141 | 26 | 260 | 1,949 | 7,389 | 17,994 |

Feedback-table footprint for the square open profiles `[R]` (one `uint8` per ordered pair):

| Profile | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|
| strict | 4 B | 4.2 KB | 0.33 MiB | 5.06 MiB | 18.83 MiB |
| extended | 4 B | 21.9 KB | 1.43 MiB | 24.41 MiB | 124.18 MiB |
| full | 4 B | 76.2 KB | 3.81 MiB | 52.80 MiB | 289.07 MiB |
| classic (G×A) | — | — | — | — | 28.64 MiB |

L1 is 2 × 2 = 4 B in every family because the `{a, i}` policy runs before the table is sized;
676 B is the pre-policy 26 × 26 figure and is not what the built profiles contain.

The 289.07 MiB full-lexicon table is the reason the memory policy exists and the reason exact DP
is not attempted there.

---

## 5. The twelve-step build pipeline

Each step is a named, idempotent stage in `src/wordle_ai/lexicon/build.py`, invoked by
`wordle-ai lex build`. Every artifact is written through a temporary sibling and replaced, and the
manifest is written last; an interrupted build therefore leaves a profile whose recorded checksums
do not match its files, which `load_profile` refuses. It does not stage a whole directory.

| # | Step | Implementation | Recorded in manifest |
|---|---|---|---|
| 1 | **Fetch or import** | `lex fetch --source scowl\\|enable\\|user`; `user` requires an explicit path and `--attest-license` flag | source id, URL/path, retrieval time |
| 2 | **Verify integrity** | SHA-256 against `sources.lock`; unknown/mismatched hash → `SourceIntegrityError` | checksum, expected checksum |
| 3 | **Parse format** | SCOWL: one word per line, `<category>-<subcategory>.<size>`, incremental semantics; ENABLE: one per line | parser id, files read |
| 4 | **Normalise** | decode (UTF-8 → Latin-1 fallback), NFC, casefold, strip outer whitespace, reject inner whitespace | encoding fallbacks, count |
| 5 | **Filter by length** | grapheme-cluster length == profile length | per-length histogram |
| 6 | **Apply validity policy** | alphabet class, proper nouns, abbreviations, possessives, digits, punctuation, single-letter whitelist | rejection counts by rule |
| 7 | **Deduplicate** | exact string equality after normalisation; first occurrence wins, source recorded | duplicates removed |
| 8 | **Record provenance** | source name/version/licence/URL/retrieval, transform chain, generator version | full block |
| 9 | **Attach frequency metadata** | optional Zipf score computed at build time *only if* the user opts in and accepts CC BY-SA obligations; otherwise omitted | prior source, opt-in flag |
| 10 | **Derive answer and guess lists** | answer list per answer policy; guess list = validity-accepted set; assert `answers ⊆ guesses` | counts, subset assertion |
| 11 | **Build indexes and tables** | sorted tuples, `answer_index`, `guess_index`, `uint8` feedback table if within budget | offsets, table checksum, bytes |
| 12 | **Export runtime data** | `lexicon.npz` (words, offsets, indices), `manifest.json`, `*.sha256` | output paths and checksums |

### 5.1 Determinism requirements

- Sorting is by Unicode code point of the normalised word; iteration never depends on set order.
- Deduplication is order-stable (first source wins, sources are processed in a fixed order).
- Table generation is deterministic and independent of worker count: parallel builds shard by
  guess index and write into preallocated rows.
- Manifest timestamps come from `SOURCE_DATE_EPOCH` when set; otherwise they are excluded from
  the content checksum. The **content** checksum covers words, tables and transform chain, not
  the timestamp.

### 5.2 Commands

```bash
wordle-ai lex fetch --source scowl --dest data/raw
wordle-ai lex fetch --source enable --dest data/raw
wordle-ai lex build --profile strict.en.5 --dialect american
wordle-ai lex verify --all                     # re-hash outputs, re-assert invariants
wordle-ai lex diff --profile strict.en.5 --manifest-old old.json   # added/removed words
wordle-ai lex inspect --profile full.en.5 --length 5 --json
```

---

## 6. Manifest and versioning

The manifest (schema in `WORDLE_AI_TECHNICAL_SPECIFICATION.md` §3.6) is the profile's identity.
Three version numbers are distinct and all appear in every benchmark record:

- `schema_version` — manifest structure version; bumping invalidates parsers.
- `generator_version` — pipeline code version; a change may legitimately change output.
- `profile_id` — human label including language, dialect and length, e.g. `strict.en.5`.
  **Never** used alone as a cache key; always paired with `manifest_sha256`.

### 6.1 Update policy

1. Sources are pinned by version **and** checksum in `sources.lock` (committed).
2. `lex fetch` refuses to overwrite a pinned file with a different checksum unless `--update` is
   passed, which rewrites the lock and prints a diff summary.
3. Building over an existing profile requires `--rebuild`; the old manifest is retained under
   `data/processed/<profile>/history/` so `lex diff` can report exactly which words entered or
   left.
4. A benchmark run stores the manifest checksum. Two runs with different checksums are never
   compared silently; the comparison report prints both.
5. Word-list churn is expected (the reference game changed answers twice). The system treats it
   as a new profile version, not as a bug.

---

## 7. Data quality tests

Each test is a real test in `tests/`, not a checklist item.

| Area | Test |
|---|---|
| Length | Every word in `answers` and `guesses` has grapheme length exactly `profile.length` |
| Alphabet | Every character is in `profile.alphabet`; no combining marks survive NFC |
| Validity | No word matches a rejected category (possessive, digit, space, hyphen, uppercase) |
| Duplicates | `len(set(words)) == len(words)` for both sets, and sorted order is strictly increasing |
| Subset | `set(answers) <= set(guesses)`; a deliberately broken fixture must raise `ProfileIntegrityError` |
| Malformed | Empty file, BOM, CRLF, Latin-1 bytes, lone surrogate, zero-width joiner, overlong line: each yields a defined error or a defined rejection count, never a crash |
| Determinism | Two builds into different temp dirs produce identical content checksums |
| Frequency | If present, Zipf values ∈ [0, 8]; `NaN`/negative rejected; absent words default to 0.0 |
| Stability | Rebuilding from the same lock produces the same checksum; a source change produces a different one and a non-empty `lex diff` |
| Table | Every table cell equals `feedback(guess, answer)`; checksum stable across workers |
| Policy counts | Manifest rejection counts sum to raw entries − accepted entries (no unaccounted losses) |
| Single-letter | L=1 profile contains exactly `{a, i}` for English, with 24 recorded exclusions |
| Coverage | For the classic profile, `answers ⊆ guesses` and counts equal 2,315 / 12,972 |

Property tests (hypothesis) generate random alphabets, lengths and word sets to assert the
invariants hold beyond the shipped fixtures — this is what protects the "length 1–5 without
five-letter assumptions" requirement.

---

## 8. Distribution policy

**Committed to the repository:** code, tests, `sources.lock`, manifests (small JSON), build
instructions, `THIRD_PARTY_NOTICES.md`, and the benchmark protocol.

**Never committed:** `data/raw/`, `data/user/`, `data/processed/`, policy artifacts derived from
user-supplied lists, and any derived wordfreq table.

**Optional release artifact:** a built open-profile bundle (strict/extended/full) with notices
and manifests, if a future decision is made to publish it. The classic profile is never included,
because its licence status is unverified.

**Attribution requirements** (must appear in `THIRD_PARTY_NOTICES.md`):

- SCOWL: copyright notice plus the full permission notice, and the statement that it is provided
  "as is" without warranty.
- ENABLE: the public-domain release statement, credited to its maintainers and contributors.
- WordNet (if used): the Princeton licence text.
- wordfreq (if installed): attribution to Robyn Speer and the Zenodo citation, plus a statement
  that its data files are CC BY-SA 4.0.
- Open English WordNet (if used): CC BY 4.0 attribution to both Princeton WordNet and the Open English WordNet team, per its `LICENSE.md`.

---

## 9. Dataset risks specific to this plan

| Risk | Mitigation |
|---|---|
| SCOWL level files read as complete lists | Pipeline encodes incremental union; manifest records the level set; test asserts a known word (`color`) present in the American profile |
| `english` used without a dialect | Build refuses a profile with `dialect=None` unless `--allow-neutral`, and warns that spellings will be missing |
| Possessives inflate lists | Apostrophe rejection counted and asserted |
| Latin-1 misread | Fallback recorded; a UTF-8 strict mode exists for user files |
| Classic lists redistributed | `data/user/` gitignored; notices state the exclusion; CI check greps for the word list in tracked files |
| Silent source update changes results | Locked checksums; benchmarks store the manifest checksum; `lex diff` required for comparisons across versions |
| Answer policy confused with validity | Separate config blocks, separate manifest fields, benchmark records both |
| Wordfreq licence breach | Runtime-only dependency, no derived CSV, explicit notice |

---

## 10. Acceptance criteria for Phase 1

1. `lex build` produces `strict.en.{1..5}`, `extended.en.{1..5}`, `full.en.{1..5}` with counts
   matching this document within ±0 (exact), or the difference is explained by a documented
   policy change.
2. `lex verify --all` exits 0 and re-derives every checksum.
3. The determinism test passes across two clean builds and across 1 vs 16 workers.
4. The classic profile loads from user files, asserts 2,315 / 12,972, and fails closed when the
   files are absent.
5. The L=1 profile contains exactly `{a, i}` and the manifest records the 24 exclusions.
6. `lex inspect` reports counts, rejection reasons and source licences without loading the
   feedback table.
7. `THIRD_PARTY_NOTICES.md` exists and contains every notice listed in §8.
8. No file under `data/` is tracked by git (verified by `git check-ignore` once the repository
   exists; until then, by `.gitignore` inspection).
