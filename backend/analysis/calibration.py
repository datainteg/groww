"""
Probability Calibration for the Decision Engine (pure NumPy, NO sklearn/scipy).

This module turns the *uncalibrated* feature vectors emitted by the decision
engine into an empirical ``P(win)`` estimate.  It is the bridge between the raw
weighted-sum "confidence" the engine currently produces and a genuine,
data-driven probability that can be used for cost/slippage-aware expectancy
gating.

Two independent tools are provided:

1. :class:`Calibrator` -- a self-contained logistic-regression model fitted by
   batch gradient descent with L2 regularisation.  It standardises features
   (z-score) internally, stores ``mean`` / ``std`` / ``coef`` / ``intercept``,
   and can be serialised to / from JSON.  This is the model that maps the full
   decision-engine feature matrix ``X`` to ``P(win)`` once a labelled
   ``signal_log`` exists.

2. :func:`platt_scale` / :func:`apply_platt` -- the classic 1-D Platt scaling
   that maps a *single* scalar score (e.g. the engine's existing confidence
   fraction) onto a calibrated probability via a sigmoid ``sigmoid(a*s + b)``.
   Useful as a cheap drop-in when only one score is available.

Design contract
---------------
- Pure: nothing here touches the DB, network, or environment at import time.
  Construction and ``fit`` are side-effect free apart from filesystem access in
  the explicit ``save`` / ``load`` helpers.
- Robust degenerate handling: empty input, a single sample, or a label vector
  with fewer than two distinct classes leaves the model *unfitted*; in that
  state :meth:`Calibrator.predict_proba` returns a flat ``0.5`` for every row so
  downstream gating fails safe (no information => no edge).
- Numerically stable: the logistic / sigmoid uses a branchless stable form to
  avoid ``exp`` overflow, and standardisation guards against zero-variance
  columns.

All probabilities are returned strictly inside the open interval ``(0, 1)`` via
a small epsilon clip so log-loss / expectancy math never sees exactly 0 or 1.
"""

from __future__ import annotations

import json
import os
from typing import Tuple

import numpy as np

__all__ = [
    "Calibrator",
    "platt_scale",
    "apply_platt",
    "stable_sigmoid",
]

# Probabilities are clipped into [_PROB_EPS, 1 - _PROB_EPS] so downstream
# log-loss / Kelly / expectancy computations never hit a hard 0 or 1.
_PROB_EPS: float = 1e-6

# Lower bound applied to per-feature standard deviation to avoid divide-by-zero
# on constant columns (which would otherwise blow up the standardisation).
_STD_FLOOR: float = 1e-8


def stable_sigmoid(z: np.ndarray) -> np.ndarray:
    """Numerically stable logistic sigmoid, element-wise.

    Uses the branchless identity that evaluates ``exp`` only on non-positive
    arguments, avoiding overflow for large positive ``z``.

    Parameters
    ----------
    z : np.ndarray
        Real-valued logits of any shape.

    Returns
    -------
    np.ndarray
        ``1 / (1 + exp(-z))`` computed stably, same shape as ``z``,
        dtype ``float64``.
    """
    z = np.asarray(z, dtype=np.float64)
    out = np.empty_like(z)
    pos = z >= 0.0
    neg = ~pos
    # For z >= 0: 1 / (1 + exp(-z)).
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    # For z <  0: exp(z) / (1 + exp(z)) -- keeps exp argument <= 0.
    exp_z = np.exp(z[neg])
    out[neg] = exp_z / (1.0 + exp_z)
    return out


def _as_2d_float(X: np.ndarray) -> np.ndarray:
    """Coerce ``X`` to a 2-D float64 array, treating 1-D as a single column.

    Parameters
    ----------
    X : np.ndarray
        Feature matrix ``(n_samples, n_features)`` or a 1-D vector of length
        ``n_samples`` (interpreted as a single feature).

    Returns
    -------
    np.ndarray
        A 2-D ``float64`` array with shape ``(n_samples, n_features)``.
    """
    arr = np.asarray(X, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    elif arr.ndim != 2:
        raise ValueError(f"X must be 1-D or 2-D, got ndim={arr.ndim}")
    return arr


class Calibrator:
    """Logistic-regression probability calibrator (pure NumPy).

    The model standardises each input feature to zero mean / unit variance,
    then fits weights ``coef`` and an ``intercept`` by minimising the
    L2-regularised binary cross-entropy via full-batch gradient descent.

    Attributes
    ----------
    mean_ : np.ndarray | None
        Per-feature training mean used for standardisation (``None`` until fit).
    std_ : np.ndarray | None
        Per-feature training std (floored at ``_STD_FLOOR``); ``None`` until fit.
    coef_ : np.ndarray | None
        Fitted weight vector in *standardised* feature space; ``None`` until fit.
    intercept_ : float
        Fitted bias term in standardised space.
    n_features_ : int | None
        Number of features seen during fit; ``None`` until fit.

    Notes
    -----
    The regularisation penalty is applied to ``coef_`` only (never the
    intercept), matching standard practice.
    """

    def __init__(self) -> None:
        self.mean_: np.ndarray | None = None
        self.std_: np.ndarray | None = None
        self.coef_: np.ndarray | None = None
        self.intercept_: float = 0.0
        self.n_features_: int | None = None

    # ------------------------------------------------------------------ #
    # State
    # ------------------------------------------------------------------ #
    @property
    def is_fitted(self) -> bool:
        """``True`` once a usable model has been fitted."""
        return (
            self.coef_ is not None
            and self.mean_ is not None
            and self.std_ is not None
            and self.n_features_ is not None
        )

    # ------------------------------------------------------------------ #
    # Training
    # ------------------------------------------------------------------ #
    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        l2: float = 1.0,
        iters: int = 500,
        lr: float = 0.1,
    ) -> "Calibrator":
        """Fit the logistic model by L2-regularised gradient descent.

        Parameters
        ----------
        X : np.ndarray
            Feature matrix ``(n_samples, n_features)`` (1-D allowed -> single
            feature).  Non-finite rows are dropped together with their labels.
        y : np.ndarray
            Binary labels of length ``n_samples``.  Any value > 0.5 is treated
            as the positive class (win), everything else as negative.
        l2 : float, default 1.0
            L2 penalty strength on the coefficients (not the intercept).
        iters : int, default 500
            Number of full-batch gradient-descent iterations.
        lr : float, default 0.1
            Learning rate.  Operating in standardised space keeps a single
            constant learning rate well-conditioned across features.

        Returns
        -------
        Calibrator
            ``self``.  If the input is empty, has a single sample, or contains
            fewer than two distinct classes after cleaning, the model is reset
            to the *unfitted* state and returned unchanged otherwise.

        Notes
        -----
        Degenerate inputs intentionally leave the model unfitted rather than
        raising, so a thin labelled log at session start cannot crash the
        engine -- :meth:`predict_proba` then falls back to ``0.5``.
        """
        self._reset()

        try:
            Xf = _as_2d_float(X)
            yf = np.asarray(y, dtype=np.float64).reshape(-1)
        except (ValueError, TypeError):
            return self

        if Xf.size == 0 or yf.size == 0 or Xf.shape[0] != yf.shape[0]:
            return self

        # Drop rows with any non-finite feature or label.
        finite_mask = np.isfinite(Xf).all(axis=1) & np.isfinite(yf)
        Xf = Xf[finite_mask]
        yf = yf[finite_mask]

        # Binarise: positive class is anything strictly greater than 0.5.
        yb = (yf > 0.5).astype(np.float64)

        n_samples, n_features = Xf.shape
        # Need >= 2 samples and both classes present, else there is no signal.
        if n_samples < 2 or np.unique(yb).size < 2:
            return self

        l2 = max(float(l2), 0.0)
        iters = max(int(iters), 1)

        mean = Xf.mean(axis=0)
        std = Xf.std(axis=0)
        std = np.where(std < _STD_FLOOR, 1.0, std)  # constant cols -> no scaling
        Xs = (Xf - mean) / std

        coef = np.zeros(n_features, dtype=np.float64)
        intercept = 0.0
        inv_n = 1.0 / float(n_samples)

        for _ in range(iters):
            logits = Xs @ coef + intercept
            preds = stable_sigmoid(logits)
            error = preds - yb  # gradient of BCE w.r.t. logits

            grad_coef = inv_n * (Xs.T @ error) + l2 * inv_n * coef
            grad_intercept = inv_n * float(error.sum())

            coef -= lr * grad_coef
            intercept -= lr * grad_intercept

            if not (np.all(np.isfinite(coef)) and np.isfinite(intercept)):
                # Divergence guard: abandon the fit and stay unfitted.
                self._reset()
                return self

        self.mean_ = mean
        self.std_ = std
        self.coef_ = coef
        self.intercept_ = float(intercept)
        self.n_features_ = int(n_features)
        return self

    # ------------------------------------------------------------------ #
    # Inference
    # ------------------------------------------------------------------ #
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return calibrated ``P(win)`` for each row of ``X``.

        Parameters
        ----------
        X : np.ndarray
            Feature matrix ``(n_samples, n_features)`` (1-D allowed -> single
            sample / single feature).

        Returns
        -------
        np.ndarray
            1-D array of probabilities in the open interval ``(0, 1)``, length
            ``n_samples``.  If the model is unfitted, the feature count does not
            match training, or any row is non-finite, that row's probability is
            ``0.5`` (no-edge fallback).
        """
        Xf = _as_2d_float(X)
        n_samples = Xf.shape[0]

        if not self.is_fitted:
            return np.full(n_samples, 0.5, dtype=np.float64)

        assert self.coef_ is not None and self.mean_ is not None
        assert self.std_ is not None and self.n_features_ is not None

        if Xf.shape[1] != self.n_features_:
            return np.full(n_samples, 0.5, dtype=np.float64)

        out = np.full(n_samples, 0.5, dtype=np.float64)
        finite_mask = np.isfinite(Xf).all(axis=1)
        if finite_mask.any():
            Xs = (Xf[finite_mask] - self.mean_) / self.std_
            logits = Xs @ self.coef_ + self.intercept_
            probs = stable_sigmoid(logits)
            out[finite_mask] = np.clip(probs, _PROB_EPS, 1.0 - _PROB_EPS)
        return out

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def save(self, path: str) -> None:
        """Serialise the model to JSON at ``path``.

        Parameters
        ----------
        path : str
            Destination file path.  Parent directories are created if missing.

        Notes
        -----
        An unfitted model is still serialised (with null arrays) so callers can
        round-trip without special-casing; :meth:`load` reconstructs the exact
        unfitted state.
        """
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)

        payload = {
            "type": "logistic_calibrator",
            "version": 1,
            "is_fitted": self.is_fitted,
            "n_features": self.n_features_,
            "mean": None if self.mean_ is None else self.mean_.tolist(),
            "std": None if self.std_ is None else self.std_.tolist(),
            "coef": None if self.coef_ is None else self.coef_.tolist(),
            "intercept": self.intercept_,
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)

    @classmethod
    def load(cls, path: str) -> "Calibrator":
        """Reconstruct a :class:`Calibrator` from a JSON file written by ``save``.

        Parameters
        ----------
        path : str
            Path to a JSON file produced by :meth:`save`.

        Returns
        -------
        Calibrator
            The deserialised model.  If the file is missing required fields or
            describes an unfitted model, an unfitted :class:`Calibrator` is
            returned (predict_proba => 0.5).
        """
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)

        model = cls()
        if not payload.get("is_fitted"):
            return model

        mean = payload.get("mean")
        std = payload.get("std")
        coef = payload.get("coef")
        n_features = payload.get("n_features")
        if mean is None or std is None or coef is None or n_features is None:
            return model

        model.mean_ = np.asarray(mean, dtype=np.float64)
        model.std_ = np.asarray(std, dtype=np.float64)
        model.coef_ = np.asarray(coef, dtype=np.float64)
        model.intercept_ = float(payload.get("intercept", 0.0))
        model.n_features_ = int(n_features)

        # Sanity: array shapes must agree, otherwise fall back to unfitted.
        if not (
            model.mean_.shape == (model.n_features_,)
            and model.std_.shape == (model.n_features_,)
            and model.coef_.shape == (model.n_features_,)
        ):
            model._reset()
        return model

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #
    def _reset(self) -> None:
        """Return the model to the pristine unfitted state."""
        self.mean_ = None
        self.std_ = None
        self.coef_ = None
        self.intercept_ = 0.0
        self.n_features_ = None


# ---------------------------------------------------------------------- #
# Platt scaling (1-D)
# ---------------------------------------------------------------------- #
def platt_scale(
    scores: np.ndarray,
    y: np.ndarray,
    l2: float = 0.0,
    iters: int = 500,
    lr: float = 0.1,
) -> Tuple[float, float]:
    """Fit 1-D Platt scaling ``P = sigmoid(a * score + b)``.

    Platt scaling calibrates a single scalar decision score (e.g. the decision
    engine's existing confidence fraction) onto a probability by fitting a
    one-feature logistic regression on the *raw* scores.

    Parameters
    ----------
    scores : np.ndarray
        1-D array of uncalibrated scalar scores, one per labelled sample.
    y : np.ndarray
        Binary labels of the same length (``> 0.5`` => positive / win).
    l2 : float, default 0.0
        Optional L2 penalty on the slope ``a``.  Defaults to 0 (unregularised,
        classic Platt).
    iters : int, default 500
        Gradient-descent iterations.
    lr : float, default 0.1
        Learning rate (scores are internally standardised for conditioning,
        then ``a`` / ``b`` are mapped back to raw-score space).

    Returns
    -------
    (a, b) : tuple[float, float]
        Slope and intercept such that ``apply_platt(scores, a, b)`` yields the
        calibrated probability on the *raw* score scale.  On degenerate input
        (empty, single sample, single class, or non-finite collapse) the
        identity-ish fallback ``(0.0, 0.0)`` is returned, which maps every
        score to ``0.5``.

    Notes
    -----
    Fitting is done in standardised space for numerical stability, then the
    coefficients are algebraically converted back:
    ``a = a_std / std`` and ``b = b_std - a_std * mean / std``.
    """
    s = np.asarray(scores, dtype=np.float64).reshape(-1)
    yf = np.asarray(y, dtype=np.float64).reshape(-1)

    if s.size == 0 or yf.size == 0 or s.shape[0] != yf.shape[0]:
        return 0.0, 0.0

    finite = np.isfinite(s) & np.isfinite(yf)
    s = s[finite]
    yf = yf[finite]
    yb = (yf > 0.5).astype(np.float64)

    if s.size < 2 or np.unique(yb).size < 2:
        return 0.0, 0.0

    mean = float(s.mean())
    std = float(s.std())
    if std < _STD_FLOOR:
        # All scores identical -> no discriminative signal.
        return 0.0, 0.0
    ss = (s - mean) / std

    a_std = 0.0
    b_std = 0.0
    n = float(s.size)
    inv_n = 1.0 / n
    l2 = max(float(l2), 0.0)
    iters = max(int(iters), 1)

    for _ in range(iters):
        preds = stable_sigmoid(a_std * ss + b_std)
        error = preds - yb
        grad_a = inv_n * float(ss @ error) + l2 * inv_n * a_std
        grad_b = inv_n * float(error.sum())
        a_std -= lr * grad_a
        b_std -= lr * grad_b
        if not (np.isfinite(a_std) and np.isfinite(b_std)):
            return 0.0, 0.0

    # Map standardised coefficients back to raw-score space.
    a = a_std / std
    b = b_std - a_std * mean / std
    return float(a), float(b)


def apply_platt(scores: np.ndarray, a: float, b: float) -> np.ndarray:
    """Apply Platt parameters to scores -> calibrated probabilities.

    Parameters
    ----------
    scores : np.ndarray
        Array of raw scalar scores of any shape.
    a : float
        Slope from :func:`platt_scale`.
    b : float
        Intercept from :func:`platt_scale`.

    Returns
    -------
    np.ndarray
        Probabilities ``sigmoid(a * scores + b)`` clipped to ``(0, 1)``, same
        shape as ``scores``, dtype ``float64``.  Non-finite inputs map to
        ``0.5``.
    """
    s = np.asarray(scores, dtype=np.float64)
    logits = float(a) * s + float(b)
    probs = stable_sigmoid(logits)
    probs = np.clip(probs, _PROB_EPS, 1.0 - _PROB_EPS)
    # Any non-finite score collapses to the neutral 0.5.
    probs = np.where(np.isfinite(s), probs, 0.5)
    return probs
