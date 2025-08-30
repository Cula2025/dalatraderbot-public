import numpy as np
import pandas as pd

def _rsi_wilder(close: pd.Series, length: int = 14) -> pd.Series:
    """RSI enligt Wilder (smoothed)."""
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)

    # Wilder smoothing = EMA med alpha = 1/length
    roll_up = up.ewm(alpha=1/length, adjust=False).mean()
    roll_down = down.ewm(alpha=1/length, adjust=False).mean()

    rs = roll_up / (roll_down.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)

def _atr14(df: pd.DataFrame) -> pd.Series:
    """ATR(14) enkel (glidande medel på True Range)."""
    h, l, c = df["High"], df["Low"], df["Close"]
    prev_c = c.shift(1)
    tr = pd.concat([
        (h - l),
        (h - prev_c).abs(),
        (l - prev_c).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    return atr

def build_signals(
    df: pd.DataFrame,
    rsi_buy: int = 52,
    rsi_sell: int = 59,
    rsi_len: int = 14,
    use_trend: bool = True,
    use_atr: bool = False,
    atr_lo: float = 0.5,
    atr_hi: float = 4.0,
) -> pd.DataFrame:
    """
    Bygger signaler:
      - RSI (valfri längd)
      - BUY när RSI < rsi_buy (med filter)
      - SELL när RSI > rsi_sell
      - Trendfilter: pris > SMA200 (om aktivt)
      - ATR-filter: ATR% inom [atr_lo, atr_hi] (om aktivt)
    Returnerar en kopia av df med kolumnerna: RSI, SMA200, ATR14, ATRpct, BUY, SELL
    """
    d = df.copy()

    # Säkerställ kolumner
    for col in ("Open","High","Low","Close","Volume"):
        if col not in d.columns:
            raise ValueError(f"Saknar kolumn '{col}' i data.")

    # Indikatorer
    d["RSI"] = _rsi_wilder(d["Close"], length=int(rsi_len))
    d["SMA200"] = d["Close"].rolling(200).mean()
    d["ATR14"] = _atr14(d)
    d["ATRpct"] = (d["ATR14"] / d["Close"]) * 100.0

    # Filter
    trend_ok = (~use_trend) | (d["Close"] > d["SMA200"])
    if use_atr:
        atr_ok = (d["ATRpct"] >= float(atr_lo)) & (d["ATRpct"] <= float(atr_hi))
    else:
        atr_ok = True

    # Bas-signaler
    buy_raw = d["RSI"] < float(rsi_buy)
    sell_raw = d["RSI"] > float(rsi_sell)

    # Applicera filter på BUY
    d["BUY"]  = (buy_raw & trend_ok & atr_ok).fillna(False)
    d["SELL"] = sell_raw.fillna(False)

    # Säkerställ bool dtype
    d["BUY"]  = d["BUY"].astype(bool)
    d["SELL"] = d["SELL"].astype(bool)

    return d
