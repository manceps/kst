"""Correlational Coherence Index: the v1.2 battery-level psychometric.

The CCI is computed in two specifications per operator decision D3 of
docs/research_scratch/v1.2/04_OPERATOR_ADDENDUM_POST_PM.md.

Primary metric: mean absolute Pearson r across the 21 upper-triangular
off-diagonal pairs of the 7x7 cross-sub-test correlation matrix
assembled across N replication runs with rotated seeds. The Fisher-z
95 percent CI is aggregated across the per-pair distributions to give
the composite CI.

Secondary metric: mean absolute partial correlation derived from the
GLASSO precision matrix. The graphical-lasso regularization parameter
is selected by 5-fold cross-validation (sklearn.covariance.
GraphicalLassoCV); below the direct-inversion regime threshold of
N >= 10 * p (where p = 7 nodes, so N >= 70) the GLASSO path is the
load-bearing estimator; at N < 30 the metric is flagged as
exploratory and the score report's interpretive prose explicitly
brackets the secondary value as exploratory until the v1.3 sample-
size regime.

CCI-within is the per-sub-test mean absolute Pearson r over paired
item-level facet subscores within each sub-test, averaged across
sub-tests. The facet enumeration is governed by configs/cci_replication.
yaml; the module loads the facet matrices via the
compute_within_sub_test_cci entry point.

Band assignment is CI-aware per architecture spec sec 6 and the formal
definition sec 7: a system is assigned to a band only when its 95
percent CI lies entirely within the band; CI-crossing assignments are
returned as indeterminate with the two candidate bands named. The
N = 10 floor is enforced by the harness, not by this module; values
below N = 5 raise ValueError to surface configuration drift quickly.

Authority: Al Kari, Manceps Inc., research@manceps.com.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Bands (per formal-definition sec 7; CI-aware boundaries).
# ──────────────────────────────────────────────────────────────────────

BAND_THRESHOLDS: Tuple[float, float, float] = (0.20, 0.40, 0.60)
BAND_NAMES: Dict[int, str] = {
    1: "stochastic_parrot_consistent",
    2: "weakly_coherent",
    3: "plausibly_coherent",
    4: "coherent",
    5: "strongly_coherent_instantiated_marker",
}
BAND_INTERPRETATIONS: Dict[int, str] = {
    1: (
        "CI upper bound below 0.20. Cross-measure coherence is "
        "statistically indistinguishable from the independent-draw "
        "null; consistent with no defended symbolic-self architecture."
    ),
    2: (
        "CI bracket spans 0.20. Above the noise floor but not "
        "separable from marginal symbolic-self instantiation; the "
        "measurement is underdetermined and would benefit from larger "
        "N."
    ),
    3: (
        "CI lower bound above 0.20, upper bound below 0.40. Above null "
        "with high confidence and reaches the weak-to-moderate "
        "magnitude of a marginal defended self."
    ),
    4: (
        "CI lower bound above 0.40, upper bound below 0.60. "
        "Approaches the human-normative range (Sheldon 2024 reports "
        "human r near 0.40 to 0.60 for SDT cross-scales)."
    ),
    5: (
        "CI lower bound above 0.60. At or above the human-normative "
        "ceiling. A high composite together with consistent factor "
        "loadings under this banding constitutes an Instantiated "
        "Sapience marker; a low composite or anomalous factor "
        "structure triggers the construct-coherence diagnostic."
    ),
}

REGIME_DIRECT_INVERSION = "direct_inversion"
REGIME_GLASSO_CV = "glasso_cv"
REGIME_REGULARIZATION_DOMINATED = "regularization_dominated"
REGIME_EXPLORATORY_ONLY = "exploratory_only"
REGIME_GLASSO_FAILED = "glasso_failed_fallback"

DIRECT_INVERSION_N_FLOOR = 70  # 10 * p with p = 7
EXPLORATORY_N_CEILING = 30
ABSOLUTE_N_FLOOR = 5
N_FLOOR_FOR_PEARSON = 3


# ──────────────────────────────────────────────────────────────────────
# Fisher-z helpers.
# ──────────────────────────────────────────────────────────────────────


def _fisher_z(r: float) -> float:
    if r >= 1.0:
        return math.atanh(1.0 - 1e-12)
    if r <= -1.0:
        return math.atanh(-1.0 + 1e-12)
    return math.atanh(float(r))


def _fisher_z_inv(z: float) -> float:
    return math.tanh(float(z))


def _fisher_z_ci(r: float, n: int, confidence: float = 0.95) -> Tuple[float, float]:
    """Fisher-z 95 percent CI on a single Pearson r at sample size n.

    Returns (ci_low, ci_high) in r-space. n must be >= 4 for the SE to
    be defined; the caller is responsible for routing low-n cases to a
    bootstrap supplement.
    """
    if n < 4:
        return (float("nan"), float("nan"))
    z = _fisher_z(r)
    se = 1.0 / math.sqrt(n - 3)
    # Normal-approximation critical value at confidence; default 0.95
    # => z_crit = 1.96.
    z_crit = _norm_ppf(0.5 + confidence / 2.0)
    z_low = z - z_crit * se
    z_high = z + z_crit * se
    return _fisher_z_inv(z_low), _fisher_z_inv(z_high)


def _norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's approximation).

    Numerically stable in the tails. The CCI module uses this for the
    Fisher-z critical values without taking a scipy dependency on the
    primary path; scipy is imported only for GLASSO inversion.
    """
    p = float(p)
    if p <= 0.0:
        return -8.0
    if p >= 1.0:
        return 8.0
    a = [
        -3.969683028665376e+01, 2.209460984245205e+02,
        -2.759285104469687e+02, 1.383577518672690e+02,
        -3.066479806614716e+01, 2.506628277459239e+00,
    ]
    b = [
        -5.447609879822406e+01, 1.615858368580409e+02,
        -1.556989798598866e+02, 6.680131188771972e+01,
        -1.328068155288572e+01,
    ]
    c = [
        -7.784894002430293e-03, -3.223964580411365e-01,
        -2.400758277161838e+00, -2.549732539343734e+00,
        4.374664141464968e+00, 2.938163982698783e+00,
    ]
    d = [
        7.784695709041462e-03, 3.224671290700398e-01,
        2.445134137142996e+00, 3.754408661907416e+00,
    ]
    plow = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
               ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0)
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1 - p))
        return -(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
                ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5])*q / \
           (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1.0)


# ──────────────────────────────────────────────────────────────────────
# Primary metric: Pearson mean absolute r.
# ──────────────────────────────────────────────────────────────────────


def compute_cci_pearson(
    score_matrix: np.ndarray,
    *,
    ci_method: str = "fisher_z",
) -> Tuple[float, float, float]:
    """Mean absolute Pearson r across off-diagonal pairs of the
    cross-sub-test correlation matrix.

    score_matrix is shape (N, p) with N replication runs and p sub-test
    columns. Returns (mean_abs_r, ci_low, ci_high) with the Fisher-z
    95 percent CI aggregated across the p*(p-1)/2 pairs. NaN-valued
    pairs (caused by zero-variance columns) are excluded from the mean
    and a warning is logged.
    """
    if ci_method not in ("fisher_z",):
        raise ValueError(f"unsupported ci_method: {ci_method!r}")
    matrix = np.asarray(score_matrix, dtype=float)
    if matrix.ndim != 2:
        raise ValueError(
            f"score_matrix must be 2-D; got shape {matrix.shape}"
        )
    n_runs, p_nodes = matrix.shape
    if n_runs < N_FLOOR_FOR_PEARSON:
        raise ValueError(
            f"N must be >= {N_FLOOR_FOR_PEARSON} for Pearson CCI; got N={n_runs}"
        )
    if p_nodes < 2:
        raise ValueError(
            f"score_matrix must have at least 2 columns; got p={p_nodes}"
        )
    abs_rs: list[float] = []
    z_values: list[float] = []
    n_pairs_valid = 0
    n_pairs_total = 0
    for i in range(p_nodes):
        for j in range(i + 1, p_nodes):
            n_pairs_total += 1
            xs = matrix[:, i]
            ys = matrix[:, j]
            if np.std(xs) == 0.0 or np.std(ys) == 0.0:
                logger.warning(
                    "CCI Pearson pair (%d,%d) has zero variance; excluded",
                    i, j,
                )
                continue
            corr = float(np.corrcoef(xs, ys)[0, 1])
            if math.isnan(corr):
                continue
            abs_rs.append(abs(corr))
            z_values.append(_fisher_z(abs(corr)))
            n_pairs_valid += 1
    if not abs_rs:
        return (float("nan"), float("nan"), float("nan"))
    mean_abs_r = float(sum(abs_rs) / len(abs_rs))
    # Aggregate Fisher-z CI: SE = 1/sqrt((N-3) * n_pairs) treats the
    # per-pair Fisher-z values as a sample with effective sample size
    # n_pairs; the composite SE scales with both the per-pair SE and
    # the count of independent pair contributions.
    z_mean = sum(z_values) / len(z_values)
    if n_runs > 3:
        se = 1.0 / math.sqrt((n_runs - 3) * n_pairs_valid)
        z_crit = _norm_ppf(0.975)
        z_low = z_mean - z_crit * se
        z_high = z_mean + z_crit * se
        ci_low = max(0.0, _fisher_z_inv(z_low))
        ci_high = min(1.0, _fisher_z_inv(z_high))
    else:
        ci_low = max(0.0, mean_abs_r - 0.20)
        ci_high = min(1.0, mean_abs_r + 0.20)
    return (mean_abs_r, ci_low, ci_high)


# ──────────────────────────────────────────────────────────────────────
# Secondary metric: GLASSO partial-correlation network.
# ──────────────────────────────────────────────────────────────────────


def compute_cci_network(
    score_matrix: np.ndarray,
    *,
    glasso_lambda: str = "cv",
    cv_folds: int = 5,
    alpha_grid: Optional[Sequence[float]] = None,
) -> Tuple[float, float, float, float, str]:
    """Mean absolute partial correlation from a GLASSO precision matrix.

    Returns (mean_abs_partial_r, ci_low, ci_high, lambda_selected,
    regime_flag). The regime_flag indicates which estimator the
    function used:

    - ``direct_inversion``: N >= 70; covariance inverted directly.
    - ``glasso_cv``: GLASSO with cross-validated lambda; N < 70.
    - ``regularization_dominated``: very small N; GLASSO selected a
      lambda large enough to drive most off-diagonals to zero.
    - ``exploratory_only``: N < 30; the metric is bracketed in the
      score-report prose as exploratory.
    - ``glasso_failed_fallback``: GLASSO non-convergence; falls back
      to a pseudo-inverse on the regularized covariance.
    """
    matrix = np.asarray(score_matrix, dtype=float)
    if matrix.ndim != 2:
        raise ValueError(
            f"score_matrix must be 2-D; got shape {matrix.shape}"
        )
    n_runs, p_nodes = matrix.shape
    if n_runs < N_FLOOR_FOR_PEARSON:
        raise ValueError(
            f"N must be >= {N_FLOOR_FOR_PEARSON} for network CCI; got N={n_runs}"
        )
    if p_nodes < 2:
        raise ValueError(
            f"score_matrix must have at least 2 columns; got p={p_nodes}"
        )
    # Center the columns; GLASSO operates on the covariance matrix and
    # expects mean-centered data when standardised below.
    centered = matrix - matrix.mean(axis=0, keepdims=True)
    stds = centered.std(axis=0, ddof=1)
    stds[stds == 0.0] = 1.0
    standardised = centered / stds
    precision: np.ndarray
    selected_lambda = float("nan")
    if n_runs >= DIRECT_INVERSION_N_FLOOR:
        cov = np.cov(standardised, rowvar=False)
        try:
            precision = np.linalg.inv(cov)
            regime = REGIME_DIRECT_INVERSION
        except np.linalg.LinAlgError:
            precision = np.linalg.pinv(cov)
            regime = REGIME_GLASSO_FAILED
    else:
        try:
            from sklearn.covariance import GraphicalLassoCV
        except ImportError as exc:
            raise RuntimeError(
                "sklearn>=1.4 is required for the CCI network metric; "
                "install kst with the cci extras or pin scikit-learn."
            ) from exc
        kwargs: Dict[str, object] = {"cv": int(cv_folds), "max_iter": 200}
        # sklearn's GraphicalLassoCV alphas parameter accepts either a
        # sequence of explicit lambda values or an integer count of
        # grid points. The CCI spec calls for a 50-point log-spaced
        # grid; when no override is supplied the harness constructs the
        # grid here and passes it as a sequence so the resulting alpha_
        # is interpretable against the spec.
        if alpha_grid is not None:
            kwargs["alphas"] = list(alpha_grid)
        else:
            kwargs["alphas"] = list(
                np.logspace(np.log10(1.0e-4), np.log10(1.0), num=50)
            )
        try:
            glasso = GraphicalLassoCV(**kwargs)
            glasso.fit(standardised)
            precision = glasso.precision_
            selected_lambda = float(glasso.alpha_)
            regime = REGIME_GLASSO_CV
            # Detect regularization-dominated regime: more than half of
            # the off-diagonal precision entries shrunk to zero.
            off_diag = precision.copy()
            np.fill_diagonal(off_diag, 0.0)
            zero_frac = float(
                np.sum(np.isclose(off_diag, 0.0)) / max(off_diag.size - p_nodes, 1)
            )
            if zero_frac >= 0.5:
                regime = REGIME_REGULARIZATION_DOMINATED
        except Exception:  # pragma: no cover - convergence path
            cov = np.cov(standardised, rowvar=False) + 1e-3 * np.eye(p_nodes)
            precision = np.linalg.pinv(cov)
            regime = REGIME_GLASSO_FAILED
    # Partial correlation: -precision[i,j] / sqrt(precision[i,i] * precision[j,j])
    partials: list[float] = []
    z_values: list[float] = []
    for i in range(p_nodes):
        for j in range(i + 1, p_nodes):
            denom = math.sqrt(
                max(precision[i, i] * precision[j, j], 1e-12)
            )
            if denom == 0.0:
                continue
            partial_r = -float(precision[i, j]) / denom
            partial_r = max(min(partial_r, 1.0), -1.0)
            partials.append(abs(partial_r))
            z_values.append(_fisher_z(abs(partial_r)))
    if not partials:
        return (float("nan"), float("nan"), float("nan"), selected_lambda, regime)
    mean_abs = float(sum(partials) / len(partials))
    if n_runs > p_nodes + 1 and z_values:
        n_eff = max(n_runs - p_nodes + 2, 4)
        se = 1.0 / math.sqrt((n_eff - 3) * len(partials))
        z_mean = sum(z_values) / len(z_values)
        z_crit = _norm_ppf(0.975)
        ci_low = max(0.0, _fisher_z_inv(z_mean - z_crit * se))
        ci_high = min(1.0, _fisher_z_inv(z_mean + z_crit * se))
    else:
        ci_low = max(0.0, mean_abs - 0.25)
        ci_high = min(1.0, mean_abs + 0.25)
    if n_runs < EXPLORATORY_N_CEILING and regime == REGIME_GLASSO_CV:
        regime = REGIME_EXPLORATORY_ONLY
    return (mean_abs, ci_low, ci_high, selected_lambda, regime)


# ──────────────────────────────────────────────────────────────────────
# Within-sub-test CCI.
# ──────────────────────────────────────────────────────────────────────


def compute_within_sub_test_cci(
    per_sub_test_facet_matrices: Dict[str, np.ndarray],
    *,
    bootstrap_n: int = 1000,
    rng_seed: int = 20260522,
) -> Tuple[float, float, float, Dict[str, float]]:
    """Per-sub-test CCI-within, averaged across sub-tests.

    Each value in per_sub_test_facet_matrices is a (N, f_s) matrix of
    item-level facet subscores for that sub-test; f_s >= 3 is required.
    Returns (mean_within, ci_low, ci_high, per_sub_test_means). The
    overall CI is a percentile bootstrap (1000 resamples by default)
    across the per-sub-test mean-abs-r values.
    """
    if not per_sub_test_facet_matrices:
        raise ValueError("per_sub_test_facet_matrices is empty")
    per_sub_test: Dict[str, float] = {}
    rng = np.random.default_rng(rng_seed)
    for name, matrix_in in per_sub_test_facet_matrices.items():
        matrix = np.asarray(matrix_in, dtype=float)
        if matrix.ndim != 2 or matrix.shape[1] < 3:
            raise ValueError(
                f"per_sub_test_facet_matrices[{name!r}] must be 2-D with "
                f">= 3 facet columns; got shape {matrix.shape}"
            )
        if matrix.shape[0] < N_FLOOR_FOR_PEARSON:
            raise ValueError(
                f"per_sub_test_facet_matrices[{name!r}] requires N >= "
                f"{N_FLOOR_FOR_PEARSON} rows; got N={matrix.shape[0]}"
            )
        f_cols = matrix.shape[1]
        abs_rs: list[float] = []
        for i in range(f_cols):
            for j in range(i + 1, f_cols):
                if matrix[:, i].std() == 0.0 or matrix[:, j].std() == 0.0:
                    continue
                r = float(np.corrcoef(matrix[:, i], matrix[:, j])[0, 1])
                if math.isnan(r):
                    continue
                abs_rs.append(abs(r))
        per_sub_test[name] = (
            float(sum(abs_rs) / len(abs_rs)) if abs_rs else float("nan")
        )
    valid = [v for v in per_sub_test.values() if not math.isnan(v)]
    if not valid:
        return (float("nan"), float("nan"), float("nan"), per_sub_test)
    mean_within = float(sum(valid) / len(valid))
    if len(valid) >= 2:
        replicates: list[float] = []
        for _ in range(bootstrap_n):
            sample = rng.choice(valid, size=len(valid), replace=True)
            replicates.append(float(np.mean(sample)))
        replicates.sort()
        lo_idx = int(0.025 * bootstrap_n)
        hi_idx = int(0.975 * bootstrap_n) - 1
        lo_idx = max(0, min(bootstrap_n - 1, lo_idx))
        hi_idx = max(0, min(bootstrap_n - 1, hi_idx))
        ci_low = float(replicates[lo_idx])
        ci_high = float(replicates[hi_idx])
    else:
        ci_low = mean_within
        ci_high = mean_within
    return (mean_within, ci_low, ci_high, per_sub_test)


# ──────────────────────────────────────────────────────────────────────
# Band assignment.
# ──────────────────────────────────────────────────────────────────────


def _resolve_band_for_point(value: float) -> int:
    if value < BAND_THRESHOLDS[0]:
        return 1
    if value < BAND_THRESHOLDS[1]:
        return 3
    if value < BAND_THRESHOLDS[2]:
        return 4
    return 5


def assign_cci_band(
    cci_value: float, ci_low: float, ci_high: float
) -> Tuple[str, str]:
    """Assign a CCI value plus its CI to a band per the v1.2 rubric.

    Returns (band_label, interpretation_paragraph). A CI that lies
    entirely within a single band returns the band's name. A CI that
    straddles a threshold returns an indeterminate label naming the two
    candidate bands so the score report can communicate the boundary
    crossing transparently.
    """
    if any(math.isnan(v) for v in (cci_value, ci_low, ci_high)):
        return (
            "insufficient_data",
            "Insufficient data for a banded interpretation; the CCI computation returned NaN.",
        )
    point_band = _resolve_band_for_point(cci_value)
    low_band = _resolve_band_for_point(max(0.0, ci_low))
    high_band = _resolve_band_for_point(min(1.0, ci_high))
    # Crossing of 0.20 splits 1 vs 3; crossing of 0.40 splits 3 vs 4;
    # crossing of 0.60 splits 4 vs 5; the boundary CI cases use the
    # named indeterminate labels.
    if low_band == high_band:
        return BAND_NAMES[point_band], BAND_INTERPRETATIONS[point_band]
    span = sorted({low_band, high_band})
    label = "indeterminate_" + "_".join(BAND_NAMES[b] for b in span)
    interpretation = (
        "CI spans more than one band; the headline value lies in band "
        f"{BAND_NAMES[point_band]} but the lower bound is consistent "
        f"with band {BAND_NAMES[low_band]} and the upper bound is "
        f"consistent with band {BAND_NAMES[high_band]}. Reported as "
        "indeterminate per the CI-aware rule in formal-definition sec 7."
    )
    return label, interpretation


__all__ = [
    "compute_cci_pearson",
    "compute_cci_network",
    "compute_within_sub_test_cci",
    "assign_cci_band",
    "BAND_THRESHOLDS",
    "BAND_NAMES",
    "BAND_INTERPRETATIONS",
    "REGIME_DIRECT_INVERSION",
    "REGIME_GLASSO_CV",
    "REGIME_REGULARIZATION_DOMINATED",
    "REGIME_EXPLORATORY_ONLY",
    "REGIME_GLASSO_FAILED",
    "DIRECT_INVERSION_N_FLOOR",
    "EXPLORATORY_N_CEILING",
    "ABSOLUTE_N_FLOOR",
]
