import yfinance as yf
import pandas as pd

def get_data(ticker: str, start: str = "2020-01-01", interval: str = "1d") -> pd.DataFrame:
    """Hämtar OHLCV-data från Yahoo Finance."""
    df = yf.download(ticker, start=start, interval=interval, progress=False, auto_adjust=False)
    if df.empty:
        raise ValueError(f"Ingen data för {ticker}. Testa t.ex. AAPL eller ERIC-B.ST")
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.dropna(inplace=True)
    return df
