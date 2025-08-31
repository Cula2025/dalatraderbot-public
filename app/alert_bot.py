
import argparse
import time
import sys
import pandas as pd
import numpy as np

# Optional Windows toast (won't crash if not installed or not on Windows)
def notify(title, msg):
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, msg, duration=5, threaded=True)
    except Exception:
        # Fallback to stdout
        print(f"[NOTIFY] {title}: {msg}")

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    series = pd.to_numeric(series, errors="coerce")
    delta = series.diff()
    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)
    roll_up = pd.Series(up, index=series.index).rolling(period).mean()
    roll_down = pd.Series(down, index=series.index).rolling(period).mean()
    rs = roll_up / roll_down
    return 100 - (100 / (1 + rs))

def macd(series: pd.Series, fast=12, slow=26, signal=9):
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    series = pd.to_numeric(series, errors="coerce")
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line

def latest_signal(close: pd.Series):
    macd_line, signal_line = macd(close)
    r = rsi(close, 14)

    # To detect crossover we need last two points
    macd_prev, macd_now = macd_line.iloc[-2], macd_line.iloc[-1]
    sig_prev, sig_now = signal_line.iloc[-2], signal_line.iloc[-1]
    r_now = r.iloc[-1]

    cross_up = (macd_prev <= sig_prev) and (macd_now > sig_now)
    cross_down = (macd_prev >= sig_prev) and (macd_now < sig_now)

    buy = cross_up and (r_now > 50)
    sell = cross_down or (r_now < 45)

    return {
        "price": float(close.iloc[-1]),
        "rsi": float(r_now),
        "macd": float(macd_now),
        "signal": float(sig_now),
        "cross_up": cross_up,
        "cross_down": cross_down,
        "BUY": bool(buy),
        "SELL": bool(sell)
    }

def run_once(symbol: str, period: str, interval: str, quiet: bool=False):
    import yfinance as yf
    data = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False)
    if data is None or data.empty:
        print("Ingen data (kontrollera symbol/period/interval).")
        return 2

    close = data["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = close.dropna()

    sig = latest_signal(close)
    price = sig["price"]

    # Compose message
    ts = str(close.index[-1])
    if sig["BUY"]:
        msg = f"{symbol} {ts}: KÖP-signal (pris ~ {price:.2f}) | MACD-kors upp & RSI {sig['rsi']:.1f}>50"
        print(msg)
        notify("KÖP-signal", msg)
        return 0
    elif sig["SELL"]:
        msg = f"{symbol} {ts}: SÄLJ-signal (pris ~ {price:.2f}) | MACD-kors ned eller RSI {sig['rsi']:.1f}<45"
        print(msg)
        notify("SÄLJ-signal", msg)
        return 1
    else:
        if not quiet:
            print(f"{symbol} {ts}: INGEN signal | Pris {price:.2f}, RSI {sig['rsi']:.1f}, MACD {sig['macd']:.4f} vs Signal {sig['signal']:.4f}")
        return 3

def main():
    ap = argparse.ArgumentParser(description="RSI+MACD alert enligt strategi (KÖP/SÄLJ)")
    ap.add_argument("--symbol", required=True, help="Ex: NANEXA.ST")
    ap.add_argument("--period", default="6mo", help="yfinance period, ex 6mo,1y,2y")
    ap.add_argument("--interval", default="1d", help="yfinance interval, ex 1d,1h,30m")
    ap.add_argument("--loop", action="store_true", help="Kör i loop")
    ap.add_argument("--seconds", type=int, default=300, help="Sekunder mellan körningar i loop")
    ap.add_argument("--quiet", action="store_true", help="Mindre utskrifter när ingen signal")
    args = ap.parse_args()

    if args.loop:
        while True:
            try:
                run_once(args.symbol, args.period, args.interval, args.quiet)
            except Exception as e:
                print("Fel vid körning:", e, file=sys.stderr)
            time.sleep(args.seconds)
    else:
        run_once(args.symbol, args.period, args.interval, args.quiet)

if __name__ == "__main__":
    main()
