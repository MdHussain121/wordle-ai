"""Independent brute-force feedback reference.

Deliberately written with a different algorithm from the production engine: it never
uses a Counter and never reserves greens in a separate pass. Instead it marks greens,
then for each remaining guess position scans the answer left to right for the first
*unused* matching letter. If the two implementations agree on every pair, the shared
result is not an artefact of a shared bug.

Test-only. Production code must not import this module.
"""

from __future__ import annotations


def reference_tiles(guess: str, answer: str) -> tuple[int, int, int]:
    if len(guess) != len(answer):
        raise ValueError("length mismatch")
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
    return tuple(tiles)


def reference_code(guess: str, answer: str) -> int:
    code = 0
    for i, tile in enumerate(reference_tiles(guess, answer)):
        code += tile * (3 ** i)
    return code
