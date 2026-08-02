"""
Scoring for probabilistic football forecasts and the bets derived from them.

The old codebase contained no evaluation code whatsoever — zero references to
log loss, Brier, calibration or backtesting — so every accuracy claim in its
documentation was unfalsifiable. Nothing ships without passing through here.

Calibration is the metric that matters most for betting. A model can rank
matches well and still lose money if its probabilities are systematically
overconfident, because Kelly staking is superlinearly sensitive to overstated p.
"""
import numpy as np

CLASSES = ("H", "D", "A")
EPS = 1e-15


def _prep(probs, outcomes):
    p = np.asarray(probs, dtype=float)
    if p.ndim != 2 or p.shape[1] != 3:
        raise ValueError(f"probs must be (n, 3) in H/D/A order, got {p.shape}")
    y = np.asarray(outcomes)
    if y.dtype.kind in "US":
        idx = {c: i for i, c in enumerate(CLASSES)}
        try:
            y = np.array([idx[v] for v in y])
        except KeyError as exc:
            raise ValueError(f"outcome {exc} is not one of {CLASSES}") from exc
    y = y.astype(int)
    if len(y) != len(p):
        raise ValueError(f"length mismatch: {len(p)} probs vs {len(y)} outcomes")
    if (p < 0).any():
        raise ValueError("probabilities must be non-negative")

    # Normalise BEFORE clipping. Clipping first would flatten any unnormalised
    # input above 1.0 to uniform (e.g. [2,1,1] -> [1,1,1]), silently turning a
    # confident forecast into a shrug and understating its score.
    totals = p.sum(axis=1, keepdims=True)
    if (totals <= 0).any():
        raise ValueError("each row must have positive total probability")
    p = p / totals
    p = np.clip(p, EPS, 1.0)
    return p / p.sum(axis=1, keepdims=True), y


def log_loss(probs, outcomes) -> float:
    """Mean negative log likelihood. The primary forecast metric."""
    p, y = _prep(probs, outcomes)
    return float(-np.mean(np.log(p[np.arange(len(y)), y])))


def brier_score(probs, outcomes) -> float:
    """Multiclass Brier: mean squared error against the one-hot outcome."""
    p, y = _prep(probs, outcomes)
    onehot = np.eye(3)[y]
    return float(np.mean(np.sum((p - onehot) ** 2, axis=1)))


def accuracy(probs, outcomes) -> float:
    p, y = _prep(probs, outcomes)
    return float(np.mean(p.argmax(axis=1) == y))


def calibration_curve(probs, outcomes, bins: int = 10) -> list:
    """
    Reliability across all three outcomes pooled.

    Returns per-bin dicts of predicted vs observed frequency. A well-calibrated
    forecast has observed ~= predicted in every bin; systematic overprediction
    is what quietly destroys a Kelly-staked bankroll.
    """
    p, y = _prep(probs, outcomes)
    flat_p = p.ravel()
    flat_hit = np.eye(3)[y].ravel()
    edges = np.linspace(0.0, 1.0, bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (flat_p >= lo) & (flat_p < hi if hi < 1.0 else flat_p <= 1.0)
        if not m.any():
            out.append({"bin_low": lo, "bin_high": hi, "n": 0,
                        "predicted": None, "observed": None, "gap": None})
            continue
        pred, obs = float(flat_p[m].mean()), float(flat_hit[m].mean())
        out.append({"bin_low": lo, "bin_high": hi, "n": int(m.sum()),
                    "predicted": pred, "observed": obs, "gap": obs - pred})
    return out


def expected_calibration_error(probs, outcomes, bins: int = 10) -> float:
    """Sample-weighted mean |observed - predicted|. Lower is better; 0 is perfect."""
    curve = [b for b in calibration_curve(probs, outcomes, bins) if b["n"]]
    total = sum(b["n"] for b in curve)
    if not total:
        return float("nan")
    return float(sum(b["n"] * abs(b["gap"]) for b in curve) / total)


def closing_line_value(entry_prices, closing_prices) -> dict:
    """
    CLV: did our price beat the closing line?

    This is the primary season metric. Over ~150 bets per arm, P&L is dominated
    by variance, but CLV converges far faster and is the standard evidence that
    an edge is real rather than lucky.

    Positive means we bought cheaper than the market's final word.
    """
    entry = np.asarray(entry_prices, dtype=float)
    close = np.asarray(closing_prices, dtype=float)
    if len(entry) != len(close):
        raise ValueError("entry and closing price arrays must be the same length")
    ok = (entry > 0) & (close > 0) & np.isfinite(entry) & np.isfinite(close)
    if not ok.any():
        return {"n": 0, "mean_clv_pct": None, "beat_close_rate": None}
    rel = (close[ok] - entry[ok]) / entry[ok]
    return {
        "n": int(ok.sum()),
        "mean_clv_pct": float(rel.mean() * 100),
        "median_clv_pct": float(np.median(rel) * 100),
        "beat_close_rate": float((rel > 0).mean()),
    }


def roi_with_bands(stakes, pnls, n_boot: int = 2000, seed: int = 42) -> dict:
    """
    ROI plus a bootstrap confidence interval.

    Reporting a bare ROI over ~150 bets invites reading noise as skill. The
    interval usually spans zero, and saying so plainly is the point.
    """
    s = np.asarray(stakes, dtype=float)
    p = np.asarray(pnls, dtype=float)
    if len(s) != len(p):
        raise ValueError("stakes and pnls must be the same length")
    if len(s) == 0 or s.sum() == 0:
        return {"n": len(s), "roi_pct": None, "ci_low": None, "ci_high": None}

    roi = p.sum() / s.sum()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(s), size=(n_boot, len(s)))
    boots = p[idx].sum(axis=1) / np.maximum(s[idx].sum(axis=1), 1e-9)
    return {
        "n": int(len(s)),
        "roi_pct": float(roi * 100),
        "ci_low": float(np.percentile(boots, 2.5) * 100),
        "ci_high": float(np.percentile(boots, 97.5) * 100),
        "total_staked": float(s.sum()),
        "total_pnl": float(p.sum()),
    }


def summarise(probs, outcomes, bins: int = 10) -> dict:
    """One-line scorecard for a set of forecasts."""
    return {
        "n": len(outcomes),
        "log_loss": round(log_loss(probs, outcomes), 4),
        "brier": round(brier_score(probs, outcomes), 4),
        "accuracy": round(accuracy(probs, outcomes), 4),
        "ece": round(expected_calibration_error(probs, outcomes, bins), 4),
    }
