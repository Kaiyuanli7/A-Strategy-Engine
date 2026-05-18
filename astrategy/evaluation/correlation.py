"""Pairwise cross-sectional correlation across multiple factors."""

from __future__ import annotations

import pandas as pd


def pairwise_factor_correlation(
    factor_scores: dict[str, dict[pd.Timestamp, pd.Series]],
    method: str = "spearman",
) -> pd.DataFrame:
    """
    Average cross-sectional rank correlation between every pair of factors,
    across all rebalance dates.

    `factor_scores` = {factor_name: {date: Series[code -> score]}}.

    Returns square DataFrame indexed and columned by factor name.
    """
    names = list(factor_scores)
    if len(names) < 2:
        return pd.DataFrame(index=names, columns=names, dtype="float64").fillna(1.0)

    # Compute pairwise per-date correlations, then average over dates.
    pair_sums: dict[tuple[str, str], float] = {}
    pair_n: dict[tuple[str, str], int] = {}
    # Union of dates that have at least 2 factors with data
    all_dates: set[pd.Timestamp] = set()
    for d_map in factor_scores.values():
        all_dates.update(d_map.keys())

    for d in sorted(all_dates):
        per_factor: dict[str, pd.Series] = {}
        for fn in names:
            s = factor_scores[fn].get(d)
            if s is not None and not s.empty:
                per_factor[fn] = s
        if len(per_factor) < 2:
            continue
        for i, a in enumerate(per_factor):
            for b in list(per_factor)[i + 1:]:
                merged = pd.concat([per_factor[a].rename("A"),
                                    per_factor[b].rename("B")], axis=1).dropna()
                if len(merged) < 5:
                    continue
                rho = merged["A"].corr(merged["B"], method=method)
                if pd.isna(rho):
                    continue
                key = (a, b)
                pair_sums[key] = pair_sums.get(key, 0.0) + float(rho)
                pair_n[key] = pair_n.get(key, 0) + 1

    out = pd.DataFrame(index=names, columns=names, dtype="float64")
    for name in names:
        out.loc[name, name] = 1.0
    for (a, b), s in pair_sums.items():
        n = pair_n[(a, b)]
        avg = s / n if n else float("nan")
        out.loc[a, b] = avg
        out.loc[b, a] = avg
    return out.astype(float)
