"""Universe loaders for CSI 300 / CSI 500 / CSI 1000 with PIT support."""

from __future__ import annotations

from astrategy.data.cache import SQLiteCache


KNOWN_INDICES: dict[str, str] = {
    "000300": "CSI 300",
    "000905": "CSI 500",
    "000852": "CSI 1000",
}


def load_universe(
    index_code: str,
    as_of: str | None = None,
    cache: SQLiteCache | None = None,
    include_ever: bool = False,
) -> list[str]:
    """
    Return universe of stock codes for `index_code`.

    Args:
        index_code: e.g. "000300"
        as_of: ISO date. If given, returns point-in-time membership (codes that
            were members on that date). If None, returns current members
            (codes with no expiry_date).
        cache: SQLiteCache instance; uses default if None.
        include_ever: if True (and as_of is None), returns the union of all codes
            ever in the index — useful for priming data for survivorship-aware
            backtests.
    """
    c = cache or SQLiteCache()
    if include_ever:
        codes = c.get_index_members_ever(index_code)
        if codes:
            return codes
    if as_of is not None:
        return c.get_index_constituents_as_of(index_code, as_of)
    # Current members: as-of "today"
    from datetime import date
    return c.get_index_constituents_as_of(index_code, date.today().isoformat())
