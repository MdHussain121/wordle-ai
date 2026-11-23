"""One-off measurement spike for the Wordle AI research corpus (Phase 0).

Purpose: replace every estimated dataset size in the deliverable documents with a
measured value. Read-only over data/raw; writes data/processed/measurements.json.

Composition rules (from SCOWL's own README, data/raw/scowl/README):
  * `<category>-words.<size>` files are INCREMENTAL per size level, so a dictionary
    of "size N" is the union over levels 10..N.
  * `english` is the neutral base list and MUST be combined with one dialect
    category (`american`, `british`, `british_z`, `canadian`, `australian`).
    It intentionally contains only one spelling per word, e.g. `color` lives in
    `american-words.10` and `colour` in `british-words.10`, neither in `english`.

Run:  python tools/measure_lexicons.py
Exit code 0 on success, 2 on missing inputs, 3 on a failed invariant.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

RAW = Path("data/raw")
OUT = Path("data/processed")
SCOWL = RAW / "scowl" / "final"
LEVELS = [10, 20, 35, 40, 50, 55, 60, 70, 80, 95]
ALPHA = re.compile(r"^[a-z]+$")
ENCODING_FALLBACKS: Counter = Counter()


def read_lines(path: Path) -> list[str]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        # SCOWL ships ISO-8859-1 text; record every fallback so the corpus can report it.
        text = raw.decode("latin-1")
        ENCODING_FALLBACKS[path.name] += 1
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def normalize(word: str) -> str:
    return unicodedata.normalize("NFC", word).casefold().strip()


def by_len(words: set[str]) -> dict[str, int]:
    c = Counter(len(w) for w in words)
    return {str(n): c.get(n, 0) for n in range(1, 6)}


def stats(words: set[str]) -> dict:
    c = Counter(len(w) for w in words)
    return {
        "total": len(words),
        "by_length": by_len(words),
        "longer_than_5": sum(n for length, n in c.items() if length > 5),
    }


def scowl_union(categories: list[str], upto: int) -> set[str]:
    """Union of the given spelling categories over size levels 10..upto."""
    out: set[str] = set()
    for name in categories:
        for lvl in LEVELS:
            if lvl > upto:
                continue
            p = SCOWL / f"{name}-words.{lvl}"
            if p.exists():
                out |= {normalize(w) for w in read_lines(p)}
    return out


def main() -> int:
    if not SCOWL.exists() or not (RAW / "enable1.txt").exists():
        print("MISSING INPUTS: SCOWL final/ or enable1.txt", file=sys.stderr)
        return 2

    result: dict = {
        "generator": "tools/measure_lexicons.py",
        "notes": (
            "Counts are of unique source entries after casefold+NFC, before validity "
            "filtering. SCOWL files are incremental; unions include levels 10..N."
        ),
        "scowl_version": (RAW / "scowl" / "VERSION").read_text(encoding="utf-8").strip(),
    }

    # ---------- SCOWL, both compositions, to document the difference ----------
    english_only = scowl_union(["english"], 95)
    american = scowl_union(["english", "american"], 95)
    british = scowl_union(["english", "british"], 95)

    result["scowl_compositions"] = {
        "english_only": stats(english_only),
        "english_plus_american": stats(american),
        "english_plus_british": stats(british),
        "american_minus_english": len(american - english_only),
        "british_minus_english": len(british - english_only),
        "american_vs_british_symmetric_difference": len(american ^ british),
    }

    non_ascii = {w for w in american if not w.isascii()}
    result["scowl_encoding_and_charset"] = {
        "latin1_fallback_files": dict(ENCODING_FALLBACKS),
        "non_ascii_entries": len(non_ascii),
        "non_ascii_samples": sorted(non_ascii)[:15],
    }

    # ---------- SCOWL size ladder (American composition) for the profile plan ----------
    ladder = {}
    for lvl in [35, 40, 50, 55, 60, 70, 80, 95]:
        ws = scowl_union(["english", "american"], lvl)
        ladder[str(lvl)] = stats(ws)
    result["scowl_american_size_ladder"] = ladder

    # ---------- ENABLE ----------
    enable = {normalize(w) for w in read_lines(RAW / "enable1.txt")}
    result["enable"] = stats(enable)
    result["enable"]["raw_lines"] = len(read_lines(RAW / "enable1.txt"))

    # ---------- Classic Wordle lists (research input; never redistributed) ----------
    def read_csv_words(path: Path) -> list[str]:
        lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if lines and not ALPHA.match(normalize(lines[0])):
            lines = lines[1:]
        return lines

    answers = {normalize(w) for w in read_csv_words(RAW / "wordle-word-bank.csv")}
    guesses = {normalize(w) for w in read_csv_words(RAW / "wordle-valid-words.csv")}
    result["wordle_classic"] = {
        "answers": stats(answers),
        "allowed_guesses": stats(guesses),
        "answers_subset_of_guesses": answers <= guesses,
        "guess_minus_answer": len(guesses - answers),
        "non_ascii_entries": len({w for w in answers | guesses if not w.isascii()}),
    }
    if not answers <= guesses:
        print("INVARIANT FAILED: answers not a subset of allowed guesses", file=sys.stderr)
        return 3

    # ---------- Validity-policy filter counts on the broadest open list ----------
    broad = american | enable
    rejected = {w for w in broad if not ALPHA.match(w)}
    result["validity_filters_on_open_broad"] = {
        "raw_entries": len(broad),
        "rejected_total": len(rejected),
        "rejected_apostrophe": sum(1 for w in rejected if "'" in w),
        "rejected_hyphen": sum(1 for w in rejected if "-" in w),
        "rejected_space": sum(1 for w in rejected if " " in w),
        "rejected_digit": sum(1 for w in rejected if any(c.isdigit() for c in w)),
        "rejected_non_ascii": sum(1 for w in rejected if not w.isascii()),
        "rejected_samples": sorted(rejected)[:10],
        "ascii_alpha_only": len(broad - rejected),
        "ascii_alpha_length_1_to_5": sum(1 for w in broad - rejected if 1 <= len(w) <= 5),
        "single_char_entries": sorted(w for w in broad - rejected if len(w) == 1),
    }

    # ---------- Profiles: measured sizes + feedback-matrix footprint ----------
    def alpha_len_sets(words: set[str]) -> dict[int, set[str]]:
        clean = {w for w in words if ALPHA.match(w)}
        return {n: {w for w in clean if len(w) == n} for n in range(1, 6)}

    profile_words = {
        "strict_scowl_american_50": scowl_union(["english", "american"], 50),
        "extended_scowl_american_80_plus_enable": scowl_union(["english", "american"], 80) | enable,
        "full_scowl_american_95_plus_enable": american | enable,
    }
    profiles: dict = {}
    for name, words in profile_words.items():
        sets = alpha_len_sets(words)
        profiles[name] = {
            str(n): {
                "words": len(ws),
                "matrix_bytes": len(ws) * len(ws),
                "matrix_mib": round(len(ws) * len(ws) / (1024 ** 2), 2),
            }
            for n, ws in sets.items()
        }
    profiles["classic_wordle"] = {
        "5": {
            "guesses": len(guesses),
            "answers": len(answers),
            "matrix_bytes": len(guesses) * len(answers),
            "matrix_mib": round(len(guesses) * len(answers) / (1024 ** 2), 2),
        }
    }
    result["profiles"] = profiles

    # ---------- Coverage of the classic game vocabulary by open lexicons ----------
    def coverage(words: set[str]) -> dict:
        return {
            "answers_covered": len(answers & words),
            "answers_total": len(answers),
            "answers_pct": round(100.0 * len(answers & words) / len(answers), 2),
            "guesses_covered": len(guesses & words),
            "guesses_total": len(guesses),
            "guesses_pct": round(100.0 * len(guesses & words) / len(guesses), 2),
        }

    result["coverage"] = {
        "scowl_american_35": coverage(scowl_union(["english", "american"], 35)),
        "scowl_american_50": coverage(scowl_union(["english", "american"], 50)),
        "scowl_american_60": coverage(scowl_union(["english", "american"], 60)),
        "scowl_american_70": coverage(scowl_union(["english", "american"], 70)),
        "scowl_american_80": coverage(scowl_union(["english", "american"], 80)),
        "enable": coverage(enable),
        "scowl_american_80_plus_enable": coverage(scowl_union(["english", "american"], 80) | enable),
        "full_open": coverage(american | enable),
    }

    missing_enable = sorted(answers - enable)
    missing_open = sorted(answers - (american | enable))
    result["classic_answers_missing"] = {
        "from_enable": {"count": len(missing_enable), "words": missing_enable},
        "from_full_open": {"count": len(missing_open), "words": missing_open},
    }

    # ---------- Deduplication between open sources ----------
    scowl80 = scowl_union(["english", "american"], 80)
    result["source_overlap"] = {
        "enable_only": len(enable - scowl80),
        "scowl80_only": len(scowl80 - enable),
        "intersection": len(enable & scowl80),
        "union": len(enable | scowl80),
    }

    # ---------- Feedback-space arithmetic (not an estimate: exact combinatorics) ----------
    result["feedback_patterns"] = {
        str(n): {"patterns_3_pow_L": 3 ** n, "fits_in_uint8": 3 ** n <= 256}
        for n in range(1, 6)
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "measurements.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # ---------- Human-readable summary ----------
    print("SCOWL", result["scowl_version"])
    print("english-only total:", len(english_only), by_len(english_only))
    print("english+american :", len(american), by_len(american))
    print("english+british  :", len(british), by_len(british))
    print("|american - english| =", len(american - english_only),
          "  |american XOR british| =", len(american ^ british))
    print()
    print("SCOWL American size ladder (total, L1..L5):")
    for k, v in ladder.items():
        print(f"  {k:>2}: {v['total']:>7}  {v['by_length']}")
    print()
    print("ENABLE:", stats(enable))
    print("classic answers:", stats(answers))
    print("classic guesses:", stats(guesses))
    print()
    print("coverage of classic answers / allowed guesses:")
    for k, v in result["coverage"].items():
        print(f"  {k:<34} {v['answers_covered']:>4}/{v['answers_total']} "
              f"({v['answers_pct']:>6}%)  {v['guesses_covered']:>5}/{v['guesses_total']} "
              f"({v['guesses_pct']:>5}%)")
    print()
    print("validity filters:", json.dumps(result["validity_filters_on_open_broad"], indent=2))
    print()
    for name, entry in profiles.items():
        print(f"profile {name}:")
        for n, v in sorted(entry.items()):
            print(f"  L={n}: {v}")
    print()
    print("classic answers missing from ENABLE:",
          result["classic_answers_missing"]["from_enable"]["count"],
          result["classic_answers_missing"]["from_enable"]["words"])
    print("classic answers missing from full open:",
          result["classic_answers_missing"]["from_full_open"]["count"],
          result["classic_answers_missing"]["from_full_open"]["words"])
    print()
    print("feedback patterns:", result["feedback_patterns"])
    print("wrote", OUT / "measurements.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
