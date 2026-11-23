"""Exact policy artifacts: build, checksum, load and verify (§7.3).

An artifact is the solved game tree, keyed by the profile digest, rules, prior and
attempt limit. It is the only thing the ``exact`` strategy reads at solve time, so it
must fail closed: a wrong profile, a different rule mode, a changed attempt limit or a
tampered tree raises ``ArtifactMismatchError`` rather than falling back silently.

The checksum covers the JSON payload with the ``sha256`` member removed, serialised
with sorted keys and no whitespace, so it is independent of file formatting and of
the platform that wrote it.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .. import __version__
from ..errors import ArtifactMismatchError
from ..types import Profile, RuleMode
from .dp import Solution

SCHEMA_VERSION = 1
#: An artifact records the solver that wrote it in the same single-sourced version the
#: run key and run provenance use, so a rebuild is identifiable without a second copy.
SOLVER_VERSION = __version__
POLICY_SUFFIX = ".policy.json"
CHECKSUM_SUFFIX = ".sha256"


def canonical_bytes(payload: dict) -> bytes:
    clone = {key: value for key, value in payload.items() if key != "sha256"}
    return json.dumps(clone, sort_keys=True, separators=(",", ":")).encode("utf-8")


def policy_digest(payload: dict) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def subset_profile(profile: Profile, limit: int | None) -> Profile:
    """The first ``limit`` answers of a profile, as a profile in its own right.

    A policy solved over a subset is a policy over a smaller answer universe: its
    candidate masks are ``limit`` bits wide, so it can only be played against those
    answers. Building the subset profile is therefore the only honest way to verify or
    play such an artifact; ``answer_set_digest`` keeps it distinct from the full one.
    """

    if limit is None or limit >= len(profile.answers):
        return profile
    if limit < 1:
        raise ValueError("limit must be >= 1")
    answers = profile.answers[:limit]
    return Profile(
        profile_id=profile.profile_id,
        language=profile.language,
        dialect=profile.dialect,
        length=profile.length,
        alphabet=profile.alphabet,
        answers=answers,
        guesses=profile.guesses,
        manifest_sha256=profile.manifest_sha256,
        source_ids=profile.source_ids,
        answer_index={word: index for index, word in enumerate(answers)},
        guess_index=dict(profile.guess_index),
    )


def answer_set_digest(profile: Profile) -> str:
    """Digest of the exact answer set a policy was solved for.

    The profile digest identifies the lexicon; this identifies the subset of answers the
    solve actually covered, so a policy solved for a subset cannot verify against the
    full profile just because both share a manifest.
    """

    payload = "\n".join(profile.answers).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def feasibility(
    profile: Profile, *, max_answers: int, max_guesses: int
) -> tuple[bool, str | None]:
    """The exact-solver gate (§7.3): a measured refusal, not a warning."""

    if len(profile.answers) > max_answers:
        return (
            False,
            f"{profile.profile_id} has {len(profile.answers)} answers, above "
            f"exact.max_answers={max_answers}",
        )
    if len(profile.guesses) > max_guesses:
        return (
            False,
            f"{profile.profile_id} has {len(profile.guesses)} guesses, above "
            f"exact.max_guesses={max_guesses}",
        )
    return True, None


def default_policy_name(
    profile_id: str, mode: RuleMode, prior: str, attempts: int
) -> str:
    # A prior id can carry parameters (``zipf:beta=0.5``); ':' is not a legal filename
    # character on Windows, so it becomes '-' and the artifact still records the exact
    # id in its payload.
    safe_prior = re.sub(r"[^A-Za-z0-9._=-]+", "-", prior).strip("-") or "uniform"
    return f"{profile_id}.{mode.value}.{safe_prior}.a{attempts}{POLICY_SUFFIX}"


def build_artifact(
    solution: Solution,
    profile: Profile,
    *,
    mode: RuleMode,
    prior: str,
    attempts: int,
    profile_sha256: str | None = None,
) -> dict:
    """Assemble a policy payload and stamp its checksum."""

    payload = {
        "schema_version": SCHEMA_VERSION,
        "profile_id": profile.profile_id,
        "profile_sha256": profile_sha256 or profile.manifest_sha256,
        "answer_set_sha256": answer_set_digest(profile),
        "answer_set_size": len(profile.answers),
        "rules": mode.value,
        "prior": prior,
        "attempts": attempts,
        "strategy": "exact",
        "solver_version": SOLVER_VERSION,
        "proven_optimal": solution.guess_set == "all",
        "guess_set": solution.guess_set,
        "expected_guesses": solution.value,
        "max_guesses": solution.max_guesses,
        "nodes": solution.nodes,
        "memo_entries": solution.memo_entries,
        "tree": solution.policy,
    }
    payload["sha256"] = policy_digest(payload)
    return payload


def save_policy(
    path: Path,
    solution: Solution,
    profile: Profile,
    *,
    mode: RuleMode = RuleMode.NORMAL,
    prior: str = "uniform",
    attempts: int = 6,
    profile_sha256: str | None = None,
) -> dict:
    """Write the payload and its sidecar checksum atomically; return the payload."""

    payload = build_artifact(
        solution,
        profile,
        mode=mode,
        prior=prior,
        attempts=attempts,
        profile_sha256=profile_sha256,
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, sort_keys=True, indent=1) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
    sidecar = path.with_name(path.name + CHECKSUM_SUFFIX)
    sidecar.write_text(payload["sha256"] + "\n", encoding="utf-8")
    return payload


def _verify_sidecar(path: Path, payload: dict) -> None:
    sidecar = path.with_name(path.name + CHECKSUM_SUFFIX)
    if sidecar.exists():
        recorded = sidecar.read_text(encoding="utf-8").strip()
        if recorded != payload["sha256"]:
            raise ArtifactMismatchError(
                f"{path}: sidecar checksum {recorded} does not match the artifact's "
                f"recorded {payload['sha256']}",
                path=str(path),
            )


def load_policy(
    path: Path,
    *,
    profile: Profile | None = None,
    mode: RuleMode | None = None,
    prior: str | None = None,
    attempts: int | None = None,
    verify: bool = True,
) -> dict:
    """Load and verify a policy artifact, returning its payload."""

    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArtifactMismatchError(f"policy artifact not found: {path}", path=str(path)) from exc
    except json.JSONDecodeError as exc:
        raise ArtifactMismatchError(
            f"{path}: not a policy artifact: {exc}", path=str(path)
        ) from exc

    if not isinstance(payload, dict) or "tree" not in payload:
        raise ArtifactMismatchError(f"{path}: missing policy tree", path=str(path))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ArtifactMismatchError(
            f"{path}: schema version {payload.get('schema_version')} is not "
            f"{SCHEMA_VERSION}",
            path=str(path),
        )
    if verify:
        recorded = payload.get("sha256")
        actual = policy_digest(payload)
        if recorded != actual:
            raise ArtifactMismatchError(
                f"{path}: policy checksum {recorded} does not match its contents {actual}",
                path=str(path),
            )
        _verify_sidecar(path, payload)
    if profile is not None:
        expected = profile.manifest_sha256
        if payload.get("profile_sha256") != expected:
            raise ArtifactMismatchError(
                f"{path}: policy was built for profile digest "
                f"{payload.get('profile_sha256')}, not {expected}",
                path=str(path),
            )
        if payload.get("profile_id") != profile.profile_id:
            raise ArtifactMismatchError(
                f"{path}: policy profile id {payload.get('profile_id')} is not "
                f"{profile.profile_id}",
                path=str(path),
            )
        expected_answers = answer_set_digest(profile)
        if payload.get("answer_set_sha256") != expected_answers:
            raise ArtifactMismatchError(
                f"{path}: policy covers {payload.get('answer_set_size')} answers, not "
                f"the {len(profile.answers)} of {profile.profile_id}",
                path=str(path),
            )
    if mode is not None and payload.get("rules") != mode.value:
        raise ArtifactMismatchError(
            f"{path}: policy rules {payload.get('rules')!r} are not {mode.value!r}",
            path=str(path),
        )
    if prior is not None and payload.get("prior") != prior:
        raise ArtifactMismatchError(
            f"{path}: policy prior {payload.get('prior')!r} is not {prior!r}",
            path=str(path),
        )
    if attempts is not None and payload.get("attempts") != attempts:
        raise ArtifactMismatchError(
            f"{path}: policy attempts {payload.get('attempts')} are not {attempts}",
            path=str(path),
        )
    return payload


def index_nodes(policy: dict) -> dict[str, dict]:
    """Map every node's candidate-set signature to that node."""

    tree = policy["tree"]
    index: dict[str, dict] = {}
    stack = [tree]
    while stack:
        node = stack.pop()
        signature = node.get("state")
        if not signature:
            raise ArtifactMismatchError("policy node is missing its state signature")
        if signature in index:
            raise ArtifactMismatchError(
                f"policy contains two nodes for candidate set {signature}"
            )
        index[signature] = node
        stack.extend(node.get("children", {}).values())
    return index


def policy_summary(payload: dict) -> dict:
    """Stable human/JSON summary without the tree."""

    return {
        "profile_id": payload.get("profile_id"),
        "profile_sha256": payload.get("profile_sha256"),
        "answer_set_sha256": payload.get("answer_set_sha256"),
        "answer_set_size": payload.get("answer_set_size"),
        "rules": payload.get("rules"),
        "prior": payload.get("prior"),
        "attempts": payload.get("attempts"),
        "strategy": payload.get("strategy"),
        "solver_version": payload.get("solver_version"),
        "proven_optimal": payload.get("proven_optimal"),
        "guess_set": payload.get("guess_set"),
        "expected_guesses": payload.get("expected_guesses"),
        "max_guesses": payload.get("max_guesses"),
        "nodes": payload.get("nodes"),
        "sha256": payload.get("sha256"),
    }
