
import argparse, time, os, json, sys
import pandas as pd
import numpy as np

STATE_FILE = "alert_state.json"

def notify(title, msg, enable=True):
    if not enable:
        print(f"[NOTIFY disabled] {title}: {msg}")
        return
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, msg, duration=5, threaded=True)
    except Exception:
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

    if len(close) < 2 or len(macd_line) < 2 or len(signal_line) < 2 or len(r) < 1:
        return None

    macd_prev, macd_now = macd_line.iloc[-2], macd_line.iloc[-1]
    sig_prev, sig_now = signal_line.iloc[-2], signal_line.iloc[-1]
    r_now = r.iloc[-1]

    cross_up = (macd_prev <= sig_prev) and (macd_now > sig_now)
    cross_down = (macd_prev >= sig_prev) and (macd_now < sig_now)

    buy = cross_up and (r_now > 50)
    sell = cross_down or (r_now < 45)

    return {
        "timestamp": str(close.index[-1]),
        "price": float(close.iloc[-1]),
        "rsi": float(r_now),
        "macd": float(macd_now),
        "signal": float(sig_now),
        "BUY": bool(buy),
        "SELL": bool(sell),
    }

def load_state(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(path, state):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Kunde inte spara state:", e, file=sys.stderr)

def check_symbol(symbol, period, interval):
    import yfinance as yf
    try:
        data = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False)
    except Exception as e:
        return symbol, None, f"Fel vid hämtning: {e}"
    if data is None or data.empty or "Close" not in data.columns:
        return symbol, None, "Tom data eller saknar 'Close'"
    close = data["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = close.dropna()
    if close.empty:
        return symbol, None, "Saknar prisdata"
    sig = latest_signal(close)
    return symbol, sig, None

def main():
    ap = argparse.ArgumentParser(description="Batch-alert för flera svenska aktier (RSI+MACD)")
    ap.add_argument("--csv", default="tickers_se.csv", help="CSV med kolumn 'symbol' (ex: NANEXA.ST)")
    ap.add_argument("--period", default="6mo")
    ap.add_argument("--interval", default="1d")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--seconds", type=int, default=600)
    ap.add_argument("--notify", action="store_true", help="Visa Windows-notiser")
    ap.add_argument("--only-signals", action="store_true", help="Skriv bara ut köp/sälj, inte 'ingen signal'")
    ap.add_argument("--sleep-between", type=float, default=1.0, help="Sekunders vila mellan symboler (rate-limit vänligt)")
    args = ap.parse_args()

    # Läs tickers
    if not os.path.exists(args.csv):
        print(f"Hittar inte {args.csv}. Skapa en CSV med header 'symbol' och dina tickers (.ST).")
        sys.exit(2)
    df = pd.read_csv(args.csv)
    if "symbol" not in df.columns or df.empty:
        print("CSV måste ha kolumnen 'symbol' och innehålla minst en rad.")
        sys.exit(2)

    state = load_state(STATE_FILE)

    def run_pass():
        nonlocal state
        for sym in df["symbol"].dropna().astype(str):
            sym = sym.strip()
            if not sym:
                continue
            symbol, sig, err = check_symbol(sym, args.period, args.interval)
            if err:
                if not args.only_signals:
                    print(f"{symbol}: {err}")
            else:
                ts = sig["timestamp"]
                price = sig["price"]
                rsi_now = sig["rsi"]
                macd_now = sig["macd"]
                macd_sig = sig["signal"]

                prev = state.get(symbol, {})
                prev_ts = prev.get("timestamp")
                prev_sig = prev.get("last_signal")  # "BUY" / "SELL" / None

                if sig["BUY"]:
                    # bara larma om ny bar eller ändrad signal
                    if prev_ts != ts or prev_sig != "BUY":
                        msg = f"{symbol} {ts}: KÖP-signal (pris ~ {price:.2f}) | MACD↑ & RSI {rsi_now:.1f}>50"
                        print(msg)
                        notify("KÖP-signal", msg, args.notify)
                        state[symbol] = {"timestamp": ts, "last_signal": "BUY"}
                elif sig["SELL"]:
                    if prev_ts != ts or prev_sig != "SELL":
                        msg = f"{symbol} {ts}: SÄLJ-signal (pris ~ {price:.2f}) | MACD↓ eller RSI {rsi_now:.1f}<45"
                        print(msg)
                        notify("SÄLJ-signal", msg, args.notify)
                        state[symbol] = {"timestamp": ts, "last_signal": "SELL"}
                else:
                    if not args.only_signals:
                        print(f"{symbol} {ts}: INGEN signal | Pris {price:.2f}, RSI {rsi_now:.1f}, MACD {macd_now:.4f} vs {macd_sig:.4f}")
                    # uppdatera timestamp så vi inte spammar nästa gång
                    state.setdefault(symbol, {})["timestamp"] = ts
                time.sleep(args.sleep_between)

        save_state(STATE_FILE, state)

    if args.loop:
        while True:
            try:
                run_pass()
            except Exception as e:
                print("Fel i loop:", e, file=sys.stderr)
            time.sleep(args.seconds)
    else:
        run_pass()

if __name__ == "__main__":
    main()
