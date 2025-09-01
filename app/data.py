import pandas as pd

def rsi(series: pd.Series, n: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))

def build_signals(df: pd.DataFrame, rsi_buy: int = 45, rsi_sell: int = 55):
    """
    Enkel RSI-strategi:
      - Köp när RSI < rsi_buy
      - Sälj när RSI > rsi_sell
    """
    df = df.copy()
    df["RSI"] = rsi(df["Close"], 14)

    buy_mask = df["RSI"] < rsi_buy
    sell_mask = df["RSI"] > rsi_sell

    df["BUY"] = buy_mask.fillna(False)
    df["SELL"] = sell_mask.fillna(False)
    return df

