from __future__ import annotations
import random
from typing import Dict, Any, List, Tuple
import numpy as np
import pandas as pd
from .backtest import run_backtest

# vitlista – så att gamla backtest-versioner inte kraschar på okända kwargs
ACCEPTED = {
    "strategy","use_trend_filter","trend_ma_type","trend_ma_window",
    "breakout_lookback","exit_lookback",
    "use_rsi_filter","rsi_window","rsi_min","rsi_max",
    "fast","slow",
    "macd_fast","macd_slow","macd_signal",
    "mom_window","mom_thresh",
    "use_bb_exit","bb_window","bb_nstd","bb_percent_b_min",
    "per_trade_pct","cost_bps","slip_bps"
}

def score_from_summary(s: Dict[str, float]) -> float:
    ret = s.get("TotalReturn", 0.0)
    dd  = abs(s.get("MaxDD", 0.0))
    sh  = s.get("SharpeD", 0.0)
    return ret - 0.3*dd + 0.2*max(0.0, sh/5)

def walk_forward_splits(df: pd.DataFrame, k: int = 5):
    n = len(df)
    fold = n // k
    out = []
    idx = df.index if isinstance(df.index, pd.DatetimeIndex) else pd.to_datetime(df["Date"])
    for i in range(k):
        a = i*fold
        b = (i+1)*fold if i < k-1 else n
        out.append((idx[a], idx[b-1]))
    return out

def optimize(df: pd.DataFrame, *, strategy: str, n_sims: int = 2000, seed: int = 42,
             wf_k: int | None = None, cost_bps: float = 0.0, slip_bps: float = 0.0) -> Dict[str, Any]:
    from .strategies import sample_params
    rng = random.Random(seed)
    best: Dict[str, Any] = {"score": -1e9}
    folds = None

    # normalisera index
    dfn = df.copy()
    if "Date" in dfn.columns:
        dfn["Date"] = pd.to_datetime(dfn["Date"], errors="coerce")
        dfn = dfn.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
        dfn = dfn.set_index("Date")

    if wf_k and wf_k > 1:
        splits = walk_forward_splits(dfn, wf_k)
        folds = [(dfn.loc[a:b].copy(), a, b) for (a, b) in splits]

    for _ in range(n_sims):
        params = sample_params(strategy, rng)
        params["cost_bps"] = cost_bps
        params["slip_bps"] = slip_bps

        # sanera okända nycklar om backtest är äldre
        pcall = {k: v for k, v in params.items() if k in ACCEPTED}

        if not folds:
            res = run_backtest(dfn.copy(), **pcall)
            score = score_from_summary(res["summary"])
        else:
            scs = []
            for fold_df, _, _ in folds:
                r = run_backtest(fold_df.copy(), **pcall)
                scs.append(score_from_summary(r["summary"]))
            score = float(np.mean(scs))

        if score > best["score"]:
            best = {"score": score, "params": pcall}

    return best