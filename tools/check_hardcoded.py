"""Code-search gate: no hardcoded dictionary path, opener, length or attempt limit.

Phase 8 criterion 6. The scan is deliberately narrow and explainable:

* an opener word as a string literal (``"salet"``, ``"roate"``, ...);
* a known profile count as a literal (2,315 / 12,972 / 4,444 / 11,411 / 17,410);
* a project data path (``data/processed``, ``data/user``, ``data/raw``) in source.

Config defaults and the tests are excluded by construction: the scan walks ``src/``
only, and the few legitimate constants (supported length, alphabet) are not on this
list. ``--json`` emits the findings.

Run:  python tools/check_hardcoded.py [--json]
Exit: 0 clean, 1 findings.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SRC = Path("src")
OPENERS = ("salet", "roate", "raise", "soare", "crane", "adieu", "audio", "slate")
COUNTS = (2315, 12972, 4444, 11411, 17410)
PATH_RE = re.compile(r"data[/\\](?:processed|raw|user)")

#: Files whose mention of a data path is the configuration default or the text of a
#: check, not a hidden lookup. Opener and profile-count patterns still apply to them.
PATH_ALLOWED = {
    "src/wordle_ai/config.py": "configuration defaults",
    "src/wordle_ai/diagnose.py": "the distribution check names the paths it verifies",
    "src/wordle_ai/lexicon/source.py": "docstring for the user-supplied destination",
    "src/wordle_ai/cli/commands/lex.py": "CLI default destinations for downloads",
}
#: Published reference figures the report compares against (not solver decisions).
REFERENCE_ALLOWED = {
    "src/wordle_ai/bench/report.py": "published comparison table (Salet, 2,315 answers)",
}
REFERENCE_KINDS = {"opener", "profile-count"}

PATTERNS = [
    ("opener", re.compile(r"[\"'](?:" + "|".join(OPENERS) + r")[\"']", re.IGNORECASE)),
    ("profile-count", re.compile(r"\b(?:" + "|".join(str(c) for c in COUNTS) + r")\b")),
    ("data-path", PATH_RE),
]


def scan(root: Path = SRC) -> list[dict]:
    findings: list[dict] = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            for kind, pattern in PATTERNS:
                normalised = str(path).replace("\\", "/")
                if kind == "data-path" and normalised in PATH_ALLOWED:
                    continue
                if kind in REFERENCE_KINDS and normalised in REFERENCE_ALLOWED:
                    continue
                if pattern.search(line):
                    findings.append(
                        {
                            "kind": kind,
                            "path": str(path),
                            "line": number,
                            "text": line.strip(),
                        }
                    )
    return findings


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    findings = scan()
    if "--json" in sys.argv:
        print(json.dumps({"findings": findings, "count": len(findings)}, indent=2))
    elif findings:
        for finding in findings:
            print(f"{finding['path']}:{finding['line']}: {finding['kind']}: {finding['text']}")
    else:
        print(
            f"code search clean: no hardcoded opener, profile count or hidden data path "
            f"in {SRC}"
        )
        for name, reason in sorted({**PATH_ALLOWED, **REFERENCE_ALLOWED}.items()):
            print(f"  allowed: {name} ({reason})")
    print(f"findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
