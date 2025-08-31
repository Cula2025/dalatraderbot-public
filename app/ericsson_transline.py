import os, warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf

# --- Inställningar ---
TICKERS = ["ERIC-B.ST", "ERIC"]   # OMX först, annars ADR
START = "2022-01-01"
BASE_CAPITAL = 10000
USE_RSI_FILTER = os.getenv("USE_RSI_FILTER","1") == "1"  # sätt 0 för att stänga av filtret

def rsi(series: pd.Series, period=14) -> pd.Series:
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs  = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def macd(series: pd.Series, fast=12, slow=26, signal=9):
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    ema_f = series.ewm(span=fast, adjust=False).mean()
    ema_s = series.ewm(span=slow, adjust=False).mean()
    line  = ema_f - ema_s
    sig   = line.ewm(span=signal, adjust=False).mean()
    return line, sig

def fetch(tick):
    df = yf.download(tick, start="2021-01-01", progress=False, auto_adjust=False)
    return df.dropna()

# Hämta data (OMX -> ADR)
used = None
df = pd.DataFrame()
for t in TICKERS:
    tmp = fetch(t)
    if not tmp.empty:
        df = tmp; used = t; break
if df.empty:
    raise SystemExit("Ingen data hämtad för ERIC-B.ST/ERIC.")

# Indikatorer (som Series)
close = df["Close"]
rsi_s = rsi(close, 14)
macd_line, macd_sig = macd(close, 12, 26, 9)

# Korsningar
up_s = (macd_line > macd_sig) & (macd_line.shift(1) <= macd_sig.shift(1))
dn_s = (macd_line < macd_sig) & (macd_line.shift(1) >= macd_sig.shift(1))

# Klipp till värden (numpy) för entydig bool-logik
open_v = df["Open"].to_numpy(dtype=float)
dates  = df.index.to_pydatetime()
rsi_v  = rsi_s.to_numpy(dtype=float)
up_v   = up_s.fillna(False).to_numpy(dtype=bool)
dn_v   = dn_s.fillna(False).to_numpy(dtype=bool)

# Begränsa perioden
mask = (pd.to_datetime(df.index) >= pd.to_datetime(START))
open_v = open_v[mask]
dates  = np.array(dates)[mask]
rsi_v  = rsi_v[mask]
up_v   = up_v[mask]
dn_v   = dn_v[mask]

parts = []
in_pos = False
qty = 0
buy_px = 0.0
capital = None
initial_capital = None

# Fills på NÄSTA dags open => loopa till näst sista index
for i in range(len(open_v)-1):
    nd = dates[i+1].date()
    nopen = float(open_v[i+1])

    buy_cond  = (not in_pos) and up_v[i] and ( (not USE_RSI_FILTER) or (not np.isnan(rsi_v[i]) and rsi_v[i] > 50) )
    sell_cond = in_pos and dn_v[i]

    if buy_cond:
        qty = int(BASE_CAPITAL // nopen)
        if qty <= 0:
            continue
        buy_px = nopen
        in_pos = True
        parts.append(f"{nd} KÖP {qty} st @ {nopen:.2f}")
        if initial_capital is None:
            initial_capital = qty * nopen
            capital = initial_capital

    elif sell_cond:
        sell_px = nopen
        parts.append(f"{nd} SÄLJ {qty} st @ {sell_px:.2f}")
        if capital is not None:
            capital += (sell_px - buy_px) * qty
        in_pos = False
        qty = 0; buy_px = 0.0

tail = f" Slutligt kapital: {capital:.2f}" if capital is not None else ""
print(" ".join(parts) + tail)

# Om inget kom ut: enkel diagnos
if not parts:
    n_up = int(up_v.sum()); n_dn = int(dn_v.sum())
    print(f"\n[DEBUG] Ticker: {used} | Rader: {len(open_v)} | Period: {dates[0].date()}→{dates[-1].date()}")
    print(f"[DEBUG] Korsningar: UP={n_up}, DN={n_dn} | RSI-filter={'PÅ' if USE_RSI_FILTER else 'AV'}")
    if n_up == 0:
        print("[DEBUG] Inga köp-korsningar (UP=0).")
    elif USE_RSI_FILTER:
        print("[DEBUG] Testa utan RSI-filter: USE_RSI_FILTER=0")
