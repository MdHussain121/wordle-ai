"""Dataset extraction from exact DP policies for Phase 6 ML distillation.

Follows WORDLE_AI_ML_RESEARCH_AND_TRAINING_PLAN.md:
- Traverses the verified policy tree to extract (state, k, guess, value) tuples.
- Strictly partitions answers by word hash into Train (70%), Val (15%), Test (15%).
- Enforces zero data leakage: train states are gathered only from train-split trajectories.
- Exports to Parquet and JSONL with SHA-256 sidecar checksums.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from ..engine.feedback import feedback_code
from ..errors import ArtifactMismatchError
from ..solver.policy import load_policy
from ..types import Profile


@dataclass(frozen=True)
class AnswerSplit:
    """Pairwise-disjoint split of answer vocabulary."""

    train: tuple[str, ...]
    validation: tuple[str, ...]
    test: tuple[str, ...]

    @property
    def total(self) -> int:
        return len(self.train) + len(self.validation) + len(self.test)

    @property
    def train_fraction(self) -> float:
        return len(self.train) / self.total if self.total else 0.0

    @property
    def val_fraction(self) -> float:
        return len(self.validation) / self.total if self.total else 0.0

    @property
    def test_fraction(self) -> float:
        return len(self.test) / self.total if self.total else 0.0


def split_answers_by_word(
    answers: Sequence[str],
    *,
    train_pct: int = 70,
    val_pct: int = 15,
    seed: str = "wordle-ai-ml-split",
) -> AnswerSplit:
    """Partition answer words into Train, Validation, and Test sets by word hash.

    This ensures the split survives rebuilds, answer reorderings, and preserves
    zero leakage between training and testing.
    """
    if train_pct <= 0 or val_pct <= 0 or (train_pct + val_pct) >= 100:
        raise ValueError(f"Invalid split percentages: train={train_pct}, val={val_pct}")

    train: list[str] = []
    val: list[str] = []
    test: list[str] = []

    for word in answers:
        digest = hashlib.sha256(f"{seed}:{word}".encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % 100
        if bucket < train_pct:
            train.append(word)
        elif bucket < train_pct + val_pct:
            val.append(word)
        else:
            test.append(word)

    split = AnswerSplit(
        train=tuple(train),
        validation=tuple(val),
        test=tuple(test),
    )
    verify_leakage(split)
    return split


def verify_leakage(split: AnswerSplit) -> None:
    """Assert zero answer overlap across all splits (Section 7 rule 1)."""
    train_set = set(split.train)
    val_set = set(split.validation)
    test_set = set(split.test)

    train_val_overlap = train_set & val_set
    train_test_overlap = train_set & test_set
    val_test_overlap = val_set & test_set

    if train_val_overlap or train_test_overlap or val_test_overlap:
        raise ValueError(
            f"Data leakage detected! "
            f"train&val={len(train_val_overlap)}, "
            f"train&test={len(train_test_overlap)}, "
            f"val&test={len(val_test_overlap)}"
        )


@dataclass
class DPRecord:
    answer: str
    split: str
    turn: int
    attempts_left: int
    state_sig: str
    candidate_count: int
    optimal_guess: str
    expected_cost: float
    is_terminal: bool


@dataclass
class MLDataset:
    profile_id: str
    manifest_sha256: str
    policy_sha256: str
    split: AnswerSplit
    trajectories: list[DPRecord]
    unique_train_states: list[dict]
    unique_val_states: list[dict]
    unique_test_states: list[dict]


def unpack_mask(hex_sig: str, num_answers: int) -> np.ndarray:
    """Unpack a packed bitmask hex string into a boolean 1D numpy array."""
    raw_bytes = bytes.fromhex(hex_sig)
    unpacked = np.unpackbits(np.frombuffer(raw_bytes, dtype=np.uint8))
    return unpacked[:num_answers].astype(bool)


def extract_dp_dataset(
    policy_path: Path,
    profile: Profile,
    *,
    split: AnswerSplit | None = None,
    verify_policy: bool = True,
) -> MLDataset:
    """Traverse the exact DP policy tree and extract all trajectory states.

    States are grouped by split, ensuring models trained on train states
    never see states unique to the test split.
    """
    policy_path = Path(policy_path)
    policy_payload = load_policy(policy_path, profile=profile, verify=verify_policy)
    tree = policy_payload["tree"]
    policy_sha = policy_payload["sha256"]

    if split is None:
        split = split_answers_by_word(profile.answers)

    verify_leakage(split)

    split_map: dict[str, str] = {}
    for w in split.train:
        split_map[w] = "train"
    for w in split.validation:
        split_map[w] = "val"
    for w in split.test:
        split_map[w] = "test"

    trajectories: list[DPRecord] = []
    # (state_sig, attempts_left) -> dict of unique state information
    train_states_dict: dict[tuple[str, int], dict] = {}
    val_states_dict: dict[tuple[str, int], dict] = {}
    test_states_dict: dict[tuple[str, int], dict] = {}

    target_code = 242  # GGGGG feedback in base 3

    for answer in profile.answers:
        s_name = split_map[answer]
        curr_node = tree
        turn = 0
        attempts_left = policy_payload.get("attempts", 6)

        while True:
            state_sig = curr_node["state"]
            optimal_guess = curr_node["guess"]
            expected_cost = float(curr_node.get("value", 0.0))
            cand_mask = unpack_mask(state_sig, len(profile.answers))
            cand_count = int(cand_mask.sum())

            code = feedback_code(optimal_guess, answer)
            is_terminal = (optimal_guess == answer) or (code == target_code)

            record = DPRecord(
                answer=answer,
                split=s_name,
                turn=turn,
                attempts_left=attempts_left,
                state_sig=state_sig,
                candidate_count=cand_count,
                optimal_guess=optimal_guess,
                expected_cost=expected_cost,
                is_terminal=is_terminal,
            )
            trajectories.append(record)

            state_key = (state_sig, attempts_left)
            state_info = {
                "state_sig": state_sig,
                "turn": turn,
                "attempts_left": attempts_left,
                "candidate_count": cand_count,
                "optimal_guess": optimal_guess,
                "expected_cost": expected_cost,
                "split": s_name,
            }

            if s_name == "train":
                train_states_dict[state_key] = state_info
            elif s_name == "val":
                val_states_dict[state_key] = state_info
            else:
                test_states_dict[state_key] = state_info

            if is_terminal:
                break

            str_code = str(code)
            if str_code not in curr_node.get("children", {}):
                raise ArtifactMismatchError(
                    f"Feedback code {str_code} not found in node children for guess "
                    f"'{optimal_guess}' against answer '{answer}' at turn {turn}"
                )

            curr_node = curr_node["children"][str_code]
            turn += 1
            attempts_left -= 1

    return MLDataset(
        profile_id=profile.profile_id,
        manifest_sha256=profile.manifest_sha256,
        policy_sha256=policy_sha,
        split=split,
        trajectories=trajectories,
        unique_train_states=list(train_states_dict.values()),
        unique_val_states=list(val_states_dict.values()),
        unique_test_states=list(test_states_dict.values()),
    )


def save_dataset_parquet(dataset: MLDataset, path: Path) -> dict:
    """Save the trajectory records and metadata to a Parquet file."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    records_data = [asdict(r) for r in dataset.trajectories]
    table = pa.Table.from_pylist(records_data)
    pq.write_table(table, path, compression="zstd")

    file_bytes = path.read_bytes()
    file_sha = hashlib.sha256(file_bytes).hexdigest()

    sidecar_path = path.with_suffix(path.suffix + ".sha256")
    sidecar_path.write_text(file_sha + "\n", encoding="utf-8")

    meta_path = path.with_suffix(path.suffix + ".meta.json")
    metadata = {
        "profile_id": dataset.profile_id,
        "manifest_sha256": dataset.manifest_sha256,
        "policy_sha256": dataset.policy_sha256,
        "total_records": len(dataset.trajectories),
        "total_train_records": sum(1 for r in dataset.trajectories if r.split == "train"),
        "total_val_records": sum(1 for r in dataset.trajectories if r.split == "val"),
        "total_test_records": sum(1 for r in dataset.trajectories if r.split == "test"),
        "unique_train_states": len(dataset.unique_train_states),
        "unique_val_states": len(dataset.unique_val_states),
        "unique_test_states": len(dataset.unique_test_states),
        "split_summary": {
            "train_answers": len(dataset.split.train),
            "val_answers": len(dataset.split.validation),
            "test_answers": len(dataset.split.test),
        },
        "sha256": file_sha,
    }
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata
