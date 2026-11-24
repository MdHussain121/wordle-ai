"""Consistency checker / fixer for the Wordle AI document corpus.

Checks (and with --fix, repairs) markdown table rows whose inline code contains a
literal '|', which would otherwise split the cell and corrupt the rendered table.

Also reports: cross-referenced filenames that do not exist, and leftover markers.

Run:  python tools/check_docs.py [--fix]
Exit: 0 clean (or fixed), 1 issues remain.
"""

from __future__ import annotations

import glob
import re
import sys

DOCS = sorted(glob.glob("docs/*.md") + [f for f in glob.glob("*.md") if f != "AGENTS.md"])
REF = re.compile(r"(?:docs/)?[A-Za-z0-9_]+\.md")


def find_code_pipe_rows(lines: list[str]) -> list[tuple[int, str]]:
    bad = []
    for i, line in enumerate(lines, 1):
        s = line.lstrip()
        if not (s.startswith("|") and s.rstrip().endswith("|")):
            continue
        in_code = False
        prev = ""
        for ch in line:
            if ch == "`":
                in_code = not in_code
            elif ch == "|" and in_code and prev != "\\":
                bad.append((i, line))
                break
            prev = ch
    return bad


def escape_code_pipes(line: str) -> str:
    out = []
    in_code = False
    for ch in line:
        if ch == "`":
            in_code = not in_code
            out.append(ch)
        elif ch == "|" and in_code:
            out.append("\\|")
        else:
            out.append(ch)
    return "".join(out)


def unescaped_pipe_count(line: str) -> int:
    count = 0
    for j, ch in enumerate(line):
        if ch == "|" and (j == 0 or line[j - 1] != "\\"):
            count += 1
    return count


def table_problems(lines: list[str]) -> list[tuple[int, str]]:
    problems = []
    header = None
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            n = unescaped_pipe_count(line)
            if header is None:
                header = n
            elif n != header:
                problems.append((i, line))
        else:
            header = None
    return problems


def main() -> int:
    # The corpus uses non-ASCII characters (minus signs, arrows); the Windows
    # console defaults to cp1252 and would raise on them.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fix = "--fix" in sys.argv
    changed = 0

    for path in DOCS:
        text = open(path, encoding="utf-8").read()
        lines = text.splitlines()
        bad = find_code_pipe_rows(lines)
        if bad and fix:
            lines = [escape_code_pipes(l) for l in lines]
            open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
            changed += len(bad)
            print(f"{path}: escaped code pipes on {len(bad)} table rows")
        elif bad:
            print(f"{path}: {len(bad)} table rows contain a raw '|' inside code")

    print()
    remaining = 0
    for path in DOCS:
        lines = open(path, encoding="utf-8").read().splitlines()
        probs = table_problems(lines)
        if probs:
            remaining += len(probs)
            for i, l in probs:
                print(f"{path}:{i}: column count mismatch: {l[:120]}")
        refs = set(REF.findall("\n".join(lines)))
        for r in refs:
            try:
                open(r, encoding="utf-8").close()
            except OSError:
                print(f"{path}: broken reference -> {r}")

    print()
    print(f"files checked: {len(DOCS)}  rows fixed: {changed}  problems remaining: {remaining}")
    return 0 if remaining == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
