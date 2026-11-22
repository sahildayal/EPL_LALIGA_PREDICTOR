"""Suite-wide fixtures."""
import pytest


@pytest.fixture(autouse=True)
def _shadow_ledger_in_tmp(monkeypatch, tmp_path):
    """
    run_stake / run_snapshot / run_settle append to the shadow ledger. Without
    this, any test driving them writes real files into data/processed/shadow,
    which the matchweek workflow then commits as evidence.
    """
    from src.market import shadow
    monkeypatch.setattr(shadow, "SHADOW_DIR", tmp_path / "shadow")
