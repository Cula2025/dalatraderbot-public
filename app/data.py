import pandas as pd
import yfinance as yf
from pandas_datareader import data as pdr

def _norm(df: pd.DataFrame) -> pd.DataFrame:
    df = df[["Open","High","Low","Close","Volume"]].copy()
    return df.dropna()

def _dl_yahoo(ticker: str, start: str, interval: str) -> pd.DataFrame:
    return yf.download(
        ticker,
        start=start,
        interval=interval,
        progress=False,
        auto_adjust=False,
        threads=False,
        repair=True,
        group_by="ticker",
    )

def _dl_yahoo_period(ticker: str, period: str, interval: str) -> pd.DataFrame:
    return yf.download(
        ticker,
        period=period,
        interval=interval,
        progress=False,
        auto_adjust=False,
        threads=False,
        repair=True,
        group_by="ticker",
    )

def _dl_stooq(ticker: str, start: str) -> pd.DataFrame:
    df = pdr.DataReader(ticker, "stooq", start=pd.to_datetime(start))
    return df.sort_index()  # äldst→nyast

def get_data(ticker: str, start: str = "2023-01-01", interval: str = "1d", source: str = "auto") -> pd.DataFrame:
    """
    Hämtar OHLCV med valbar källa:
      source='auto'  : Stooq först om interval='1d', annars Yahoo; med fallbacks.
      source='stooq' : Bara Stooq (daglig data).
      source='yahoo' : Bara Yahoo (med fallbacks).
    """
    # 1) Källval
    if source == "stooq":
        try:
            df = _dl_stooq(ticker, start)
            if not df.empty:
                return _norm(df)
        except Exception:
            pass
        raise ValueError(f"Ingen Stooq-data för {ticker}")

    if source == "yahoo":
        # Försök med start/interval
        try:
            df = _dl_yahoo(ticker, start, interval)
            if not df.empty:
                return _norm(df)
        except Exception:
            pass
        # Fallback: period-baserade
        for period in ("5y", "2y", "1y"):
            try:
                dfp = _dl_yahoo_period(ticker, period, interval if interval != "1h" else "1d")
                if not dfp.empty:
                    return _norm(dfp)
            except Exception:
                pass
        raise ValueError(f"Ingen Yahoo-data för {ticker}")

    # source == "auto"
    if interval == "1d":
        # Stooq först (daglig data är stabilt här)
        try:
            df = _dl_stooq(ticker, start)
            if not df.empty:
                return _norm(df)
        except Exception:
            pass

    # Yahoo som alternativ eller för intraday
    try:
        df = _dl_yahoo(ticker, start, interval)
        if not df.empty:
            return _norm(df)
    except Exception:
        pass
    for period in ("5y", "2y", "1y"):
        try:
            dfp = _dl_yahoo_period(ticker, period, interval if interval != "1h" else "1d")
            if not dfp.empty:
                return _norm(dfp)
        except Exception:
            pass

    # Sista chans: om dagsdata — Stooq igen
    if interval == "1d":
        try:
            df = _dl_stooq(ticker, start)
            if not df.empty:
                return _norm(df)
        except Exception:
            pass

    raise ValueError(f"Ingen data för {ticker}. Testa AAPL, MSFT, SPY eller ERIC-B.ST.")
