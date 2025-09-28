from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional

import numpy as np
import pandas as pd


# ========= Indikatorer =========
def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0).rolling(window).mean()
    down = (-delta.clip(upper=0)).rolling(window).mean()
    rs = up / down.replace(0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.fillna(50.0)

def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()

def macd(close: pd.Series, fast: int=12, slow: int=26, signal:int=9) -> Tuple[pd.Series,pd.Series,pd.Series]:
    m = ema(close, fast) - ema(close, slow)
    s = ema(m, signal)
    h = m - s
    return m, s, h

def bb_percent_b(close: pd.Series, window:int=20, nstd:float=2.0) -> pd.Series:
    mid = close.rolling(window).mean()
    std = close.rolling(window).std(ddof=0)
    upper = mid + nstd*std
    lower = mid - nstd*std
    pctb = (close - lower) / (upper - lower)
    return pctb.clip(0, 1)

def atr(df: pd.DataFrame, window:int=14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([(h-l).abs(), (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(window).mean()


# ========= Parametrar =========
@dataclass
class Params:
    # RSI
    use_rsi_filter: bool = True
    rsi_window: int      = 14
    rsi_min: float       = 25.0
    rsi_max: float       = 60.0

    # Trend-gate
    use_trend_filter: bool = True
    trend_ma_type:   str   = "EMA"
    trend_ma_window: int   = 100

    # Donchian breakout/exit
    breakout_lookback: int = 55   # 0 = av
    exit_lookback:     int = 20   # 0 = av

    # MACD
    use_macd_filter: bool = False
    macd_fast:  int = 12
    macd_slow:  int = 26
    macd_signal:int = 9

    # Bollinger %B (mean-reversion gate)
    use_bb_filter: bool = False
    bb_window: int = 20
    bb_nstd: float = 2.0
    bb_min: float  = 0.2   # kräv %B <= bb_min vid entry om på

    # Stop-loss
    use_stop_loss: bool = False
    stop_mode: str      = "pct"   # "pct" | "atr"
    stop_loss_pct: float = 0.08
    atr_window: int      = 14
    atr_mult: float      = 2.0


# ========= Hjälp =========
def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    x = pd.DataFrame(df).copy()
    if "Date" not in x.columns:
        idx = x.index.name or "Date"
        x = x.reset_index().rename(columns={idx: "Date"})
    x["Date"] = pd.to_datetime(x["Date"], errors="coerce")
    for c in ("Open","High","Low","Close","Volume"):
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x.dropna(subset=["Date","Close"]).sort_values("Date").reset_index(drop=True)
    return x

def _compute_signals(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    x = df.copy()

    # Bas
    x["RSI"] = rsi(x["Close"], p.rsi_window)

    if p.use_trend_filter and p.trend_ma_window > 0:
        x["TREND"] = ema(x["Close"], p.trend_ma_window)
    else:
        x["TREND"] = np.nan

    if p.use_macd_filter:
        _, _, h = macd(x["Close"], p.macd_fast, p.macd_slow, p.macd_signal)
        x["MACD_H"] = h
    else:
        x["MACD_H"] = 0.0

    if p.use_bb_filter:
        x["PCTB"] = bb_percent_b(x["Close"], p.bb_window, p.bb_nstd)
    else:
        x["PCTB"] = 0.5

    # Donchian
    if p.breakout_lookback > 0:
        x["HH"] = x["High"].rolling(p.breakout_lookback).max()
    else:
        x["HH"] = np.nan
    if p.exit_lookback > 0:
        x["LL"] = x["Low"].rolling(p.exit_lookback).min()
    else:
        x["LL"] = np.nan

    # Villkor
    cond_trend = (not p.use_trend_filter) | (x["Close"] > x["TREND"])
    cond_macd  = (not p.use_macd_filter)  | (x["MACD_H"] > 0)
    cond_bb    = (not p.use_bb_filter)    | (x["PCTB"] <= p.bb_min)

    # RSI korsningar
    rsi_up   = (x["RSI"].shift(1) < p.rsi_min) & (x["RSI"] >= p.rsi_min)
    rsi_down = (x["RSI"].shift(1) > p.rsi_max) & (x["RSI"] <= p.rsi_max)

    # Breakout
    bo_active = p.breakout_lookback > 0
    bo_ok     = x["High"] >= x["HH"] if bo_active else pd.Series(True, index=x.index)
    ex_bo     = x["Low"]  <= x["LL"] if p.exit_lookback > 0 else pd.Series(False, index=x.index)

    # **Entry OR-logik**: RSI-kors eller (om aktivt) breakout – plus övriga filter
    x["BUY"]  = (rsi_up | (bo_active & bo_ok)) & cond_trend & cond_macd & cond_bb
    # Exit: RSI ned-kors eller Donchian-exit
    x["SELL"] = (rsi_down | ex_bo)

    return x

# ========= Backtest =========
def run_backtest(df: pd.DataFrame, p: Params) -> Dict[str, Any]:
    x = _normalize_df(df)
    x = _compute_signals(x, p)

    cash = 100_000.0
    pos  = 0.0
    entry_px = 0.0
    entry_time = None

    eq_curve: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []

    atr_ser = atr(x, p.atr_window) if (p.use_stop_loss and p.stop_mode == "atr") else None

    for i, row in x.iterrows():
        px = float(row["Close"])
        # Equity
        eq_curve.append({"Date": row["Date"], "Equity": cash + pos*px})

        # Stop-loss
        if pos > 0 and p.use_stop_loss:
            if p.stop_mode == "pct":
                stop = entry_px * (1.0 - p.stop_loss_pct)
            else:
                a = float(atr_ser.iloc[i]) if atr_ser is not None else 0.0
                stop = entry_px - p.atr_mult * a
            if px <= stop:
                cash += pos * px
                trades.append({
                    "EntryTime": entry_time, "EntryPrice": entry_px,
                    "ExitTime": row["Date"], "ExitPrice": px,
                    "PnL": pos*(px-entry_px), "reason": "StopLoss"
                })
                pos = 0.0
                entry_px = 0.0
                entry_time = None
                continue

        # Exit
        if pos > 0 and bool(row["SELL"]):
            cash += pos * px
            trades.append({
                "EntryTime": entry_time, "EntryPrice": entry_px,
                "ExitTime": row["Date"], "ExitPrice": px,
                "PnL": pos*(px-entry_px), "reason": "SignalExit"
            })
            pos = 0.0
            entry_px = 0.0
            entry_time = None
            continue

        # Entry
        if pos == 0 and bool(row["BUY"]):
            pos = cash / px   # all-in
            entry_px = px
            entry_time = row["Date"]
            cash = 0.0

    # Stäng på slutet
    if pos > 0:
        px = float(x.iloc[-1]["Close"])
        cash += pos*px
        trades.append({
            "EntryTime": entry_time, "EntryPrice": entry_px,
            "ExitTime": x.iloc[-1]["Date"], "ExitPrice": px,
            "PnL": pos*(px-entry_px), "reason": "EoP"
        })
        pos = 0.0

    eq_df = pd.DataFrame(eq_curve).dropna()
    final_eq = float(eq_df["Equity"].iloc[-1]) if not eq_df.empty else 100_000.0
    tr_dec = final_eq/100_000.0 - 1.0

    c0, c1 = float(x["Close"].iloc[0]), float(x["Close"].iloc[-1])
    buyhold = c1/c0 - 1.0

    roll_max = eq_df["Equity"].cummax() if not eq_df.empty else pd.Series([100_000.0])
    dd = (eq_df["Equity"]/roll_max) - 1.0 if not eq_df.empty else pd.Series([0.0])
    maxdd = float(dd.min()) if not dd.empty else 0.0

    ret = eq_df["Equity"].pct_change().dropna()
    sharpe_d = float(np.sqrt(252) * (ret.mean() / (ret.std() + 1e-9))) if not ret.empty else 0.0

    years = max(1e-9, (x["Date"].iloc[-1] - x["Date"].iloc[0]).days / 365.25)
    cagr = (final_eq/100_000.0) ** (1/years) - 1.0

    return {
        "summary": {
            "Bars": len(x),
            "Trades": len(trades),
            "TotalReturn": tr_dec,
            "MaxDD": maxdd,
            "SharpeD": sharpe_d,
            "BuyHold": buyhold,
            "FinalEquity": final_eq,
            "CAGR": cagr,
        },
        "equity": eq_df,
        "trades": pd.DataFrame(trades),
    }
