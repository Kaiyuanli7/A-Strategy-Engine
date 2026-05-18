"""Tests for point-in-time index membership."""

from pathlib import Path

import pandas as pd
import pytest

from astrategy.data.cache import SQLiteCache
from astrategy.data.synthetic import generate_synthetic_index_history
from astrategy.data.universes import load_universe


@pytest.fixture
def cache_with_history(tmp_path: Path) -> SQLiteCache:
    db = str(tmp_path / "test.db")
    cache = SQLiteCache(db)
    history = generate_synthetic_index_history(
        "000300", "2022-01-01", "2025-12-31", n_members=50
    )
    rows = [
        (c, eff, None if pd.isna(exp) else exp)
        for c, eff, exp in history.itertuples(index=False, name=None)
    ]
    cache.upsert_index_members("000300", rows)
    return cache


def test_synthetic_index_has_turnover():
    history = generate_synthetic_index_history(
        "000300", "2022-01-01", "2025-12-31", n_members=50
    )
    # Total unique members > initial roster size (because of turnover)
    assert history["member_code"].nunique() > 50
    # Some have expiry_date populated (delisted/removed)
    removed = history[history["expiry_date"].notna()]
    assert len(removed) > 0


def test_as_of_returns_members_active_at_date(cache_with_history: SQLiteCache):
    early_count = len(cache_with_history.get_index_constituents_as_of("000300", "2022-06-30"))
    late_count = len(cache_with_history.get_index_constituents_as_of("000300", "2025-06-30"))
    # Roster size should be ~stable (50 with quarterly turnover)
    assert 30 <= early_count <= 60
    assert 30 <= late_count <= 60


def test_as_of_excludes_expired_members(cache_with_history: SQLiteCache):
    history = cache_with_history.get_index_member_history("000300")
    expired_rows = history[history["expiry_date"].notna()]
    assert len(expired_rows) > 0
    # Pick a removed member; assert it's in the universe BEFORE expiry but not after
    sample = expired_rows.iloc[0]
    code = sample["member_code"]
    expiry = sample["expiry_date"]
    # day before expiry: should be present (if effective_date <= that)
    eff = sample["effective_date"]
    if eff < expiry:
        before = (pd.Timestamp(expiry) - pd.Timedelta(days=1)).date().isoformat()
        if before >= eff:
            assert code in cache_with_history.get_index_constituents_as_of("000300", before)
    # day on or after expiry: should NOT be present
    assert code not in cache_with_history.get_index_constituents_as_of("000300", expiry)


def test_pit_vs_current_snapshot_differ(cache_with_history: SQLiteCache):
    """The whole point: PIT membership is NOT the same as today's universe."""
    early = set(cache_with_history.get_index_constituents_as_of("000300", "2022-06-30"))
    today = set(cache_with_history.get_index_constituents_as_of("000300", "2025-12-31"))
    # Some overlap expected, but should NOT be identical (turnover applied)
    assert early != today
    # Some symmetric difference (members in one but not the other)
    assert len(early ^ today) >= 2


def test_members_ever_is_superset(cache_with_history: SQLiteCache):
    ever = set(cache_with_history.get_index_members_ever("000300"))
    early = set(cache_with_history.get_index_constituents_as_of("000300", "2022-06-30"))
    late = set(cache_with_history.get_index_constituents_as_of("000300", "2025-12-31"))
    assert early <= ever
    assert late <= ever


def test_load_universe_with_cache(cache_with_history: SQLiteCache):
    codes = load_universe("000300", as_of="2024-06-30", cache=cache_with_history)
    assert len(codes) > 0
    assert all(isinstance(c, str) for c in codes)
