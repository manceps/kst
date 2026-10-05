"""Unit tests for the CCI scoring module (v1.2)."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import yaml

from kst.score_cci import (
    ABSOLUTE_N_FLOOR,
    BAND_NAMES,
    BAND_THRESHOLDS,
    DIRECT_INVERSION_N_FLOOR,
    REGIME_DIRECT_INVERSION,
    REGIME_EXPLORATORY_ONLY,
    REGIME_GLASSO_CV,
    assign_cci_band,
    compute_cci_network,
    compute_cci_pearson,
    compute_within_sub_test_cci,
)


@pytest.fixture(scope="module")
def strong_signal_matrix() -> np.ndarray:
    rng = np.random.default_rng(20260522)
    N, p = 30, 7
    latent = rng.normal(0.0, 1.0, size=N)
    noise = rng.normal(0.0, 0.3, size=(N, p))
    return latent.reshape(-1, 1) + noise


@pytest.fixture(scope="module")
def null_signal_matrix() -> np.ndarray:
    rng = np.random.default_rng(20260523)
    return rng.normal(0.0, 1.0, size=(30, 7))


def test_pearson_strong_signal_lands_in_high_band(
    strong_signal_matrix: np.ndarray,
) -> None:
    mean_r, lo, hi = compute_cci_pearson(strong_signal_matrix)
    assert mean_r > 0.7
    assert 0.0 <= lo <= mean_r <= hi <= 1.0


def test_pearson_null_signal_lands_in_low_band(
    null_signal_matrix: np.ndarray,
) -> None:
    mean_r, lo, hi = compute_cci_pearson(null_signal_matrix)
    assert mean_r < 0.35


def test_pearson_rejects_low_n() -> None:
    with pytest.raises(ValueError):
        compute_cci_pearson(np.zeros((2, 7)))


def test_pearson_rejects_too_few_columns() -> None:
    with pytest.raises(ValueError):
        compute_cci_pearson(np.zeros((10, 1)))


def test_network_metric_matches_direct_inversion_regime() -> None:
    rng = np.random.default_rng(42)
    N = DIRECT_INVERSION_N_FLOOR
    p = 7
    latent = rng.normal(0.0, 1.0, size=N)
    noise = rng.normal(0.0, 0.3, size=(N, p))
    matrix = latent.reshape(-1, 1) + noise
    mean_p, lo, hi, lam, regime = compute_cci_network(matrix)
    assert regime == REGIME_DIRECT_INVERSION
    assert math.isnan(lam) or lam == 0.0
    assert 0.0 <= mean_p <= 1.0


def test_network_metric_uses_glasso_at_low_n() -> None:
    rng = np.random.default_rng(7)
    N = 30
    p = 7
    latent = rng.normal(0.0, 1.0, size=N)
    noise = rng.normal(0.0, 0.3, size=(N, p))
    matrix = latent.reshape(-1, 1) + noise
    mean_p, lo, hi, lam, regime = compute_cci_network(matrix)
    # N=30 sits in the GLASSO regime; the flag may be either glasso_cv or
    # regularization_dominated depending on lambda selection.
    assert regime in (
        REGIME_GLASSO_CV,
        "regularization_dominated",
    )


def test_network_metric_flags_exploratory_at_low_n() -> None:
    rng = np.random.default_rng(11)
    N = 10
    p = 7
    latent = rng.normal(0.0, 1.0, size=N)
    noise = rng.normal(0.0, 0.3, size=(N, p))
    matrix = latent.reshape(-1, 1) + noise
    _, _, _, _, regime = compute_cci_network(matrix)
    assert regime in (REGIME_EXPLORATORY_ONLY, "regularization_dominated")


def test_within_sub_test_cci_with_known_facets() -> None:
    rng = np.random.default_rng(31)
    N = 30
    facets = {
        "KMR-Adv": rng.normal(0, 1, size=(N, 5)),
        "ROT-5": rng.normal(0, 1, size=(N, 3)),
        "BWD": rng.normal(0, 1, size=(N, 5)),
    }
    mean, lo, hi, per_sub_test = compute_within_sub_test_cci(facets)
    assert 0.0 <= mean <= 1.0
    assert 0.0 <= lo <= mean <= hi <= 1.0
    assert set(per_sub_test.keys()) == {"KMR-Adv", "ROT-5", "BWD"}


def test_within_rejects_insufficient_facets() -> None:
    with pytest.raises(ValueError):
        compute_within_sub_test_cci({"KMR-Adv": np.zeros((30, 2))})


def test_within_rejects_insufficient_N() -> None:
    with pytest.raises(ValueError):
        compute_within_sub_test_cci({"KMR-Adv": np.zeros((2, 5))})


def test_band_assignment_at_threshold_boundaries() -> None:
    band, _ = assign_cci_band(0.10, 0.05, 0.15)
    assert band == "stochastic_parrot_consistent"
    band, _ = assign_cci_band(0.30, 0.25, 0.35)
    assert band == "plausibly_coherent"
    band, _ = assign_cci_band(0.50, 0.45, 0.55)
    assert band == "coherent"
    band, _ = assign_cci_band(0.80, 0.70, 0.90)
    assert band == "strongly_coherent_instantiated_marker"


def test_band_assignment_indeterminate_when_ci_spans_threshold() -> None:
    band, text = assign_cci_band(0.25, 0.15, 0.35)
    assert band.startswith("indeterminate")
    assert "stochastic_parrot_consistent" in band
    assert "plausibly_coherent" in band


def test_band_thresholds_are_canonical() -> None:
    assert BAND_THRESHOLDS == (0.20, 0.40, 0.60)
    assert set(BAND_NAMES.keys()) == {1, 2, 3, 4, 5}


def test_default_n_is_ten_in_replication_config() -> None:
    """Guard against config drift on the operator decision (2026-05-22).

    The CCI replication config is the binding contract for the v1.2
    baseline; the default N=10 must remain exactly 10 with the seed
    list [17, 23, 29, 31, 37, 41, 43, 47, 53, 59]. Any change to either
    value requires the operator-decided amendment per FIXUP_DEFAULT_N.md.
    """
    repo_root = Path(__file__).resolve().parents[2]
    config_path = repo_root / "configs" / "cci_replication.yaml"
    with config_path.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    assert config["n_replications_default"] == 10
    assert config["seeds"]["n10"] == [17, 23, 29, 31, 37, 41, 43, 47, 53, 59]
    assert len(config["seeds"]["n10"]) == 10
    assert config["modes"]["default"]["replications"] == 10
    assert config["modes"]["floor"]["replications"] == 5
    assert config["modes"]["anchor"]["replications"] == 30


def test_absolute_n_floor_constant() -> None:
    assert ABSOLUTE_N_FLOOR == 5
