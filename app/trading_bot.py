import argparse
import numpy as np
import pandas as pd

# ---- Indikatorer ----
def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    # Säkerställ 1D Series
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    series = series.astype(float)

    delta = series.diff()
    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)

    roll_up = pd.Series(up, index=series.index).rolling(period).mean()
    roll_down = pd.Series(down, index=series.index).rolling(period).mean()
    rs = roll_up / roll_down
    return 100 - (100 / (1 + rs))

def macd(series: pd.Series, fast=12, slow=26, signal=9):
    # Säkerställ 1D Series
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    series = series.astype(float)

    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line

# ---- Strategi ----
def generate_signals(close: pd.Series) -> pd.DataFrame:
    # Säkerställ 1D Series
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = pd.to_numeric(close, errors="coerce").dropna()

    macd_line, signal_line = macd(close)
    rsi14 = rsi(close, 14)

    signals = pd.DataFrame(index=close.index)
    signals["close"] = close
    signals["macd"] = macd_line
    signals["signal"] = signal_line
    signals["rsi"] = rsi14

    # Köp/sälj logik
    signals["buy"] = (signals["macd"] > signals["signal"]) & (signals["rsi"] > 50)
    signals["sell"] = (signals["macd"] < signals["signal"]) | (signals["rsi"] < 45)

    return signals.dropna()

# ---- Backtest ----
def backtest(symbol: str, period: str, interval: str):
    import yfinance as yf
    data = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False)
    if data is None or data.empty:
        print("Ingen data. Kontrollera symbol/period/interval.")
        return

    # Ibland blir 'Close' en DataFrame (MultiIndex-kolumner). Hämta första kolumnen om så.
    close = data["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    signals = generate_signals(close)

    cash = 10000.0
    shares = 0
    for date, row in signals.iterrows():
        price = float(row["close"])
        if row["buy"] and shares == 0:
            shares = int(cash // price)
            if shares > 0:
                cash -= shares * price
                print(f"{date.date()} KÖP {shares} st @ {price:.2f}")
        elif row["sell"] and shares > 0:
            cash += shares * price
            print(f"{date.date()} SÄLJ {shares} st @ {price:.2f}")
            shares = 0

    # Avsluta
    if shares > 0:
        last_price = float(signals["close"].iloc[-1])
        cash += shares * last_price
        shares = 0
    print(f"Slutligt kapital: {cash:.2f}")

# ---- CLI ----
def main():
    parser = argparse.ArgumentParser(description="Mini Trader-Bot")
    parser.add_argument("mode", choices=["backtest"], help="Körläge")
    parser.add_argument("--symbol", required=True, help="Ticker, t.ex. NANEXA.ST")
    parser.add_argument("--period", default="6mo", help="Ex: 6mo,1y,2y")
    parser.add_argument("--interval", default="1d", help="Ex: 1d,1wk")
    args = parser.parse_args()

    if args.mode == "backtest":
        backtest(args.symbol, args.period, args.interval)

if __name__ == "__main__":
    main()
