import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, yfinance as yf

# --------- PARAMETRAR ----------
TICKER = "ERIC-B.ST"      # ADR: "ERIC"
START  = "2022-01-01"

# Entry-filter
RSI_THRESH = 55
RSI_SLOPE  = 5
USE_BREAKOUT = False

# Stoppar (alla aktiva; vi tar MAX av nivåerna)
STOP_FIXED_PCT  = 8.0
STOP_TRAIL_PCT  = 12.0
ATR_MULT        = 3.0

# Position
BASE_CAPITAL = 10000
FEE_PCT_EACH_SIDE = 0.0

# --------- HJÄLPFUNKTIONER ----------
def ema(series, span): return series.ewm(span=span, adjust=False).mean()

def macd(series):
    line = ema(series, 12) - ema(series, 26)
    sig  = ema(line, 9)
    hist = line - sig
    return line, sig, hist

def rsi(series, period=14):
    d  = series.diff()
    up = d.clip(lower=0)
    dn = (-d).clip(lower=0)
    au = up.ewm(alpha=1/period, adjust=False).mean()
    ad = dn.ewm(alpha=1/period, adjust=False).mean()
    rs = au / ad.replace(0, np.nan)
    return 100 - (100/(1+rs))

def atr(df, period=14):
    h,l,c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([(h-l), (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# --------- DATA & INDIKATORER ----------
df = yf.download(TICKER, start="2021-01-01", progress=False, auto_adjust=False).dropna()
if df.empty: raise SystemExit("Ingen data hämtad.")
df = df[df.index >= pd.to_datetime(START)].copy()

close = df["Close"]
macd_line, macd_sig, macd_hist = macd(close)
rsi14 = rsi(close, 14)
sma50  = close.rolling(50).mean()
sma200 = close.rolling(200).mean()
atr14  = atr(df, 14)
hi20   = close.rolling(20).max()

cross_up = (macd_line > macd_sig) & (macd_line.shift(1) <= macd_sig.shift(1))
cross_dn = (macd_line < macd_sig) & (macd_line.shift(1) >= macd_sig.shift(1))

trend_ok    = (close > sma200) & (sma50 > sma200) & (sma200 > sma200.shift(5))
momentum_ok = (rsi14 > RSI_THRESH) & (rsi14 > rsi14.rolling(RSI_SLOPE).mean()) & (macd_hist > 0) & (macd_hist.shift(1) > 0)
breakout_ok = (close >= hi20) if USE_BREAKOUT else pd.Series(True, index=df.index)

buy_cond_s  = (cross_up & trend_ok & momentum_ok & breakout_ok).fillna(False)
sell_cond_s = cross_dn.fillna(False)

# ---- TVINGA 1D-ARRAYER ----
open_v  = np.asarray(df["Open"].values, dtype=float).reshape(-1)
high_v  = np.asarray(df["High"].values, dtype=float).reshape(-1)
low_v   = np.asarray(df["Low"].values,  dtype=float).reshape(-1)
dates_v = np.asarray(df.index.to_pydatetime()).reshape(-1)
atr_v   = np.asarray(atr14.values, dtype=float).reshape(-1)

buy_v   = np.asarray(buy_cond_s.values,  dtype=bool).reshape(-1)
sell_v  = np.asarray(sell_cond_s.values, dtype=bool).reshape(-1)

# --------- BACKTEST MED STOPPAR ----------
parts, trades, capital_curve = [], [], []

in_pos = False
qty = 0
entry_px = 0.0
entry_date = None
high_water = None
fixed_stop = None
exit_on_next_open = False
pending_exit_reason = ""

initial_capital = None
capital = None

N = len(open_v)
for i in range(N-1):
    # 0) Exit på nästa öppning
    if in_pos and exit_on_next_open:
        px = float(open_v[i+1])
        parts.append(f"{dates_v[i+1].date()} SÄLJ {qty} st @ {px:.2f}")
        fee_in  = entry_px * (FEE_PCT_EACH_SIDE/100.0)
        fee_out = px       * (FEE_PCT_EACH_SIDE/100.0)
        pnl = ( (px-fee_out) - (entry_px+fee_in) ) * qty
        capital += pnl
        capital_curve.append({"date": dates_v[i+1].date(), "capital": capital})
        trades.append({
            "entry_date": entry_date.date(), "entry_price": round(entry_px,4),
            "exit_date":  dates_v[i+1].date(), "exit_price": round(px,4),
            "qty": qty, "reason": pending_exit_reason
        })
        in_pos=False; qty=0; entry_px=0.0; entry_date=None
        high_water=None; fixed_stop=None; exit_on_next_open=False; pending_exit_reason=""

    # 1) Stoppar intradag
    if in_pos:
        high_water = max(high_water, float(high_v[i]))
        trail_stop = high_water * (1 - STOP_TRAIL_PCT/100.0)
        atr_today  = float(atr_v[i]) if not np.isnan(atr_v[i]) else 0.0
        chand_stop = high_water - atr_today*ATR_MULT
        stop_level = max(fixed_stop, trail_stop, chand_stop)
        if float(low_v[i]) <= stop_level:
            px = float(stop_level)
            parts.append(f"{dates_v[i].date()} SÄLJ {qty} st @ {px:.2f}")
            fee_in  = entry_px * (FEE_PCT_EACH_SIDE/100.0)
            fee_out = px       * (FEE_PCT_EACH_SIDE/100.0)
            pnl = ( (px-fee_out) - (entry_px+fee_in) ) * qty
            capital += pnl
            capital_curve.append({"date": dates_v[i].date(), "capital": capital})
            trades.append({
                "entry_date": entry_date.date(), "entry_price": round(entry_px,4),
                "exit_date":  dates_v[i].date(),  "exit_price": round(px,4),
                "qty": qty, "reason": "STOP"
            })
            in_pos=False; qty=0; entry_px=0.0; entry_date=None
            high_water=None; fixed_stop=None
            continue

    # 2) ENTRY på nästa öppning om villkor idag
    if (not in_pos) and bool(buy_v[i]):
        n_open = float(open_v[i+1])
        q = int(BASE_CAPITAL // n_open)
        if q > 0:
            qty = q
            entry_px = n_open
            entry_date = dates_v[i+1]
            in_pos = True
            high_water = entry_px
            fixed_stop = entry_px * (1 - STOP_FIXED_PCT/100.0)
            parts.append(f"{dates_v[i+1].date()} KÖP {qty} st @ {entry_px:.2f}")
            if initial_capital is None:
                initial_capital = qty * entry_px
                capital = initial_capital

    # 3) SÄLJ-signal → exit nästa öppning
    if in_pos and bool(sell_v[i]):
        exit_on_next_open = True
        pending_exit_reason = "SIGNAL"

# --------- OUTPUT ----------
trans_line = " ".join(parts)
if capital is not None:
    trans_line += f" Slutligt kapital: {capital:.2f}"
print(trans_line)

# Summering
if trades:
    tdf = pd.DataFrame(trades)
    rets, for_pl = [], []
    for _, tr in tdf.iterrows():
        ep, xp = tr["entry_price"], tr["exit_price"]
        rets.append((xp/ep - 1)*100)
        for_pl.append((xp-ep)*tr["qty"])
    tdf["net_return_pct"] = np.round(rets, 3)
    wins = int((tdf["net_return_pct"]>0).sum())
    print("\n--- Summering (med stopp) ---")
    print(f"Antal affärer: {len(tdf)} | Träff%: {wins/len(tdf)*100:.1f}%")
    print(f"Bästa: {tdf['net_return_pct'].max():.2f}% | Sämsta: {tdf['net_return_pct'].min():.2f}% | Snitt: {tdf['net_return_pct'].mean():.2f}%")
    if initial_capital is not None:
        print(f"Startkapital (infererat): {initial_capital:.2f}")
    if capital is not None:
        print(f"Slutligt kapital (realiserat): {capital:.2f}")
else:
    print("\n(Inga affärer enligt filtren.)")

# Spara CSV
out_dir = "/app/output"
import os; os.makedirs(out_dir, exist_ok=True)
pd.DataFrame(trades).to_csv(f"{out_dir}/ERICSSON_trades_filters_stops.csv", index=False)
pd.DataFrame(capital_curve).to_csv(f"{out_dir}/ERICSSON_capital_curve_filters_stops.csv", index=False)
