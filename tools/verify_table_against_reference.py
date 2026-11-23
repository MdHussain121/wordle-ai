"""Check every cell of a built feedback table against an independent reference.

The test suite checks feedback exhaustively at L=1..4 and on a stratified L=5 sample
(running all 30M classic cells under pytest would add over a minute to every run). This
script performs the full L=5 check on demand, which is what the Phase 1 completion
criterion "every cell matches the reference" requires.

Usage:
    python tools/verify_table_against_reference.py --profile-dir data/processed/classic.en.5

Exit code 0 means every cell matched; 1 means at least one mismatch (the first five are
printed); 2 means the profile or table is missing.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wordle_ai.engine.table import FeedbackTable  # noqa: E402
from wordle_ai.lexicon.profile import load_profile  # noqa: E402


def reference_code(guess: str, answer: str) -> int:
    """Independent two-pass reference: greens first, then unused-copy yellows."""

    length = len(guess)
    tiles = [0] * length
    used = [False] * length
    for i in range(length):
        if guess[i] == answer[i]:
            tiles[i] = 2
            used[i] = True
    for i in range(length):
        if tiles[i] == 2:
            continue
        for j in range(length):
            if not used[j] and answer[j] == guess[i]:
                tiles[i] = 1
                used[j] = True
                break
    code = 0
    for i, tile in enumerate(tiles):
        code += tile * (3 ** i)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-dir", type=Path, required=True)
    parser.add_argument("--limit-rows", type=int, default=0, help="0 means every row.")
    args = parser.parse_args()

    profile = load_profile(args.profile_dir)
    table_path = args.profile_dir / "feedback.npy"
    if not table_path.exists():
        print(f"missing feedback table: {table_path}", file=sys.stderr)
        return 2
    table = FeedbackTable(table_path, profile, lru_rows=0)

    rows = range(len(profile.guesses)) if args.limit_rows <= 0 else range(
        min(args.limit_rows, len(profile.guesses))
    )
    started = time.perf_counter()
    checked = 0
    mismatches = 0
    for row_index in rows:
        guess = profile.guesses[row_index]
        row = table.row_index(row_index)
        for answer_index, answer in enumerate(profile.answers):
            actual = int(row[answer_index])
            expected = reference_code(guess, answer)
            if actual != expected:
                mismatches += 1
                if mismatches <= 5:
                    print(f"MISMATCH guess={guess} answer={answer} table={actual} reference={expected}")
            checked += 1
        if row_index % 2000 == 0:
            elapsed = time.perf_counter() - started
            print(f"  {row_index}/{len(profile.guesses)} rows, {checked:,} cells, {elapsed:.1f}s", flush=True)

    elapsed = time.perf_counter() - started
    print(f"checked={checked:,} mismatches={mismatches} elapsed={elapsed:.1f}s")
    return 0 if mismatches == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
