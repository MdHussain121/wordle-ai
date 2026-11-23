"""Phase 5: priors, prior-aware scoring, cache identity and the calibration gate (§8)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from wordle_ai.bench.calibration import (
    DEFAULT_BETA_GRID,
    calibrate_prior,
    calibrate_zipf,
    fit_beta,
    split_answers,
)
from wordle_ai.engine.prior import (
    EmpiricalPrior,
    UniformPrior,
    ZipfPrior,
    normalised_weights,
    parse_prior_id,
)
from wordle_ai.engine.state import new_game
from wordle_ai.engine.table import ComputedRows
from wordle_ai.errors import PriorCalibrationError, WordleError
from wordle_ai.solver.policy import load_policy, policy_digest
from wordle_ai.strategy import get_strategy
from wordle_ai.types import PriorKind, Profile, RuleMode

WORDS_2 = ("aa", "ab", "ba", "bb")


def tiny_profile() -> Profile:
    return Profile(
        profile_id="tiny.ab.2",
        language="ab",
        dialect=None,
        length=2,
        alphabet="ab",
        answers=WORDS_2,
        guesses=WORDS_2,
        manifest_sha256="0" * 64,
        answer_index={word: i for i, word in enumerate(WORDS_2)},
        guess_index={word: i for i, word in enumerate(WORDS_2)},
    )


# ---- priors -------------------------------------------------------------------


def test_uniform_and_zero_beta_are_bit_identical():
    profile = tiny_profile()
    uniform = UniformPrior().weights(profile)
    zero = ZipfPrior(0.0).weights(profile)
    assert np.array_equal(uniform, zero)
    assert not np.array_equal(uniform, ZipfPrior(0.5).weights(profile))


def test_normalised_weights_sum_to_one_and_preserve_order():
    profile = tiny_profile()
    prior = UniformPrior()
    weights = normalised_weights(prior, profile)
    assert weights.shape == (4,)
    assert weights.sum() == pytest.approx(1.0, abs=1e-12)
    assert np.array_equal(weights, np.full(4, 0.25))


def test_zipf_requires_a_non_negative_beta():
    with pytest.raises(PriorCalibrationError):
        ZipfPrior(-0.1)


def test_zipf_prior_is_finite_and_non_negative(strict_profiles):
    pytest.importorskip("wordfreq")
    profile = strict_profiles["strict.en.2"]
    weights = normalised_weights(ZipfPrior(0.5), profile)
    assert weights.shape == (len(profile.answers),)
    assert np.all(weights >= 0)
    assert weights.sum() == pytest.approx(1.0, abs=1e-12)
    # A temperature orders words by frequency: the most likely word is not the
    # alphabetically first one unless the profile happens to agree.
    assert np.argmax(weights) == int(np.argmax(ZipfPrior(0.5).weights(profile)))


def test_empirical_prior_is_laplace_smoothed(tmp_path):
    profile = tiny_profile()
    history = tmp_path / "history.txt"
    history.write_text("aa\naa\nbb\n# comment\n", encoding="utf-8")
    prior = EmpiricalPrior(history)
    weights = prior.weights(profile)
    # Counts: aa=2, ab=0, ba=0, bb=1, alpha=1.
    assert np.allclose(weights, [3.0, 1.0, 1.0, 2.0])
    assert prior.prior_id.startswith("empirical:")
    assert prior.kind is PriorKind.EMPIRICAL


def test_empirical_prior_rejects_a_missing_history(tmp_path):
    with pytest.raises(PriorCalibrationError):
        EmpiricalPrior(tmp_path / "nope.txt")


def test_parse_prior_id_accepts_the_documented_forms(tmp_path):
    assert parse_prior_id("uniform").prior_id == "uniform"
    assert parse_prior_id("").prior_id == "uniform"
    assert parse_prior_id("zipf").prior_id == "zipf"
    assert parse_prior_id("zipf:0.5").prior_id == "zipf:beta=0.5"
    assert parse_prior_id("zipf:beta=1").prior_id == "zipf:beta=1"
    history = tmp_path / "history.txt"
    history.write_text("aa\n", encoding="utf-8")
    assert parse_prior_id(f"empirical:{history}").kind is PriorKind.EMPIRICAL
    for bad in ("zipf:-1", "zipf:hot", "nope", "empirical:"):
        with pytest.raises(WordleError):
            parse_prior_id(bad)


# ---- state and strategies -----------------------------------------------------


def test_posterior_honours_the_prior_and_sums_to_one():
    profile = tiny_profile()
    prior = np.array([0.7, 0.1, 0.1, 0.1])
    state = new_game(profile, prior_weights=prior)
    assert state.posterior.sum() == pytest.approx(1.0, abs=1e-12)
    assert state.posterior[0] == pytest.approx(0.7)
    solved = state.apply("aa", _pattern("aa", "aa"))
    assert solved.posterior.sum() == pytest.approx(1.0)


def _pattern(guess: str, answer: str):
    from wordle_ai.engine.feedback import feedback_pattern

    return feedback_pattern(guess, answer)


def test_weighted_entropy_equals_entropy_at_beta_zero(strict_profiles):
    profile = strict_profiles["strict.en.2"]
    rows = ComputedRows(profile)
    state = new_game(profile)
    plain = get_strategy("entropy").choose(state, rows)
    prior = normalised_weights(ZipfPrior(0.0), profile)
    weighted = get_strategy("weighted_entropy", prior_weights=prior).choose(state, rows)
    assert weighted.guess == plain.guess
    assert weighted.breakdown["entropy"] == pytest.approx(plain.breakdown["entropy"], abs=1e-12)


def test_weighted_entropy_scores_change_under_a_sharp_prior(strict_profiles):
    profile = strict_profiles["strict.en.2"]
    rows = ComputedRows(profile)
    state = new_game(profile)
    strategy = get_strategy("weighted_entropy")
    uniform = {entry.guess: entry.score for entry in strategy.score(state, rows)}
    concentrated = np.full(len(profile.answers), 1e-9)
    concentrated[profile.answer_index_of(profile.answers[0])] = 1.0
    sharp = {
        entry.guess: entry.score for entry in strategy.score(state, rows, prior=concentrated)
    }
    # The same guess must be scored differently: the prior reaches the objective, not
    # just the endgame branch.
    assert any(abs(uniform[word] - sharp[word]) > 1e-9 for word in uniform)
    assert strategy.choose(state, rows, prior=concentrated).guess in profile.guess_index


def test_bayes_cost_minimises_the_analytic_one_step_cost():
    profile = tiny_profile()
    rows = ComputedRows(profile)
    state = new_game(profile, max_attempts=6)
    decision = get_strategy("bayes_cost").choose(state, rows)
    assert decision.breakdown["branch"] in {"bayes_cost", "single_candidate"}
    # Recompute sum_r p_r sqrt(|S_r|) for the chosen guess from the feedback table.
    counts = np.bincount(rows.row(decision.guess), minlength=profile.pattern_count)
    expected = float((counts * np.sqrt(counts)).sum() / counts.sum())
    assert decision.breakdown["bayes_cost"] == pytest.approx(expected, abs=1e-12)


def test_decision_cache_separates_priors():
    """Two priors must never share a cached decision, even on the same state."""

    profile = tiny_profile()
    rows = ComputedRows(profile)
    state = new_game(profile, max_attempts=2)  # endgame branch: argmax posterior
    cache: dict = {}
    strategy = get_strategy("expected_remaining")
    first = strategy.choose(state, rows, prior=np.array([0.9, 0.1, 0.0, 0.0]), cache=cache)
    second = strategy.choose(state, rows, prior=np.array([0.0, 0.0, 0.1, 0.9]), cache=cache)
    assert first.guess == "aa"
    assert second.guess == "bb"


def test_prior_with_no_mass_on_candidates_is_refused():
    profile = tiny_profile()
    rows = ComputedRows(profile)
    with pytest.raises(ValueError):
        get_strategy("expected_remaining").choose(
            new_game(profile), rows, prior=np.zeros(4)
        )


# ---- policy artifacts ---------------------------------------------------------


def test_policy_built_under_one_prior_is_refused_under_another(tmp_path):
    payload = {
        "schema_version": 1,
        "profile_id": "tiny.ab.2",
        "profile_sha256": "0" * 64,
        "answer_set_sha256": "",
        "answer_set_size": 4,
        "rules": RuleMode.NORMAL.value,
        "prior": "uniform",
        "attempts": 6,
        "strategy": "exact",
        "solver_version": "test",
        "proven_optimal": True,
        "guess_set": "all",
        "expected_guesses": 3.0,
        "max_guesses": 4,
        "nodes": 1,
        "memo_entries": 1,
        "tree": {"state": "0", "guess": "aa", "value": 3.0, "children": {}},
    }
    payload["sha256"] = policy_digest(payload)
    path = tmp_path / "tiny.policy.json"
    import json

    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_policy(path, prior="uniform")["prior"] == "uniform"
    with pytest.raises(Exception) as excinfo:
        load_policy(path, prior="zipf:beta=0.5")
    assert "prior" in str(excinfo.value)


# ---- calibration gate ---------------------------------------------------------


def test_split_is_deterministic_and_disjoint(strict_profiles):
    profile = strict_profiles["strict.en.2"]
    first = split_answers(profile)
    second = split_answers(profile)
    assert first == second
    assert set(first.validation).isdisjoint(first.test)
    assert len(first.validation) + len(first.test) == len(profile.answers)


def test_uniform_prior_is_rejected_by_the_gate(strict_profiles):
    profile = strict_profiles["strict.en.2"]
    verdict = calibrate_prior(profile, UniformPrior())
    assert verdict["admitted"] is False
    assert "not better than uniform" in verdict["reject_reason"]
    assert verdict["test"]["log_loss"] == pytest.approx(
        verdict["uniform_on_test"]["log_loss"], abs=1e-12
    )


def test_zipf_fit_uses_the_validation_half_and_reports_the_test_half(strict_profiles):
    pytest.importorskip("wordfreq")
    profile = strict_profiles["strict.en.2"]
    verdict = calibrate_zipf(profile, grid=(0.0, 0.5, 1.0))
    assert verdict["fit"]["best_beta"] in (0.0, 0.5, 1.0)
    assert verdict["test"]["samples"] + verdict["split"]["validation"] == len(profile.answers)
    assert "ece" in verdict["test"]
    # A verdict is one of the two acceptable outcomes, and both are recorded.
    if verdict["admitted"]:
        assert verdict["test"]["log_loss"] < verdict["uniform_on_test"]["log_loss"]
        assert verdict["test"]["ece"] < 0.05
    else:
        assert verdict["reject_reason"]


def test_beta_fit_never_reads_the_test_half(strict_profiles):
    pytest.importorskip("wordfreq")
    profile = strict_profiles["strict.en.2"]
    split = split_answers(profile)
    fit = fit_beta(profile, grid=(0.0, 1.0), split=split)
    assert [row["beta"] for row in fit["grid"]] == [0.0, 1.0]
    # Recomputing the validation loss by hand must agree with the reported value.
    weights = normalised_weights(ZipfPrior(1.0), profile)
    expected = float(
        np.mean([-math.log(weights[index]) for index in split.validation])
    )
    assert fit["grid"][1]["validation_log_loss"] == pytest.approx(expected, abs=1e-12)
