import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, yfinance as yf

# --------- PARAMETRAR ----------
TICKER = "NANEXA.ST"
START  = "2022-01-01"

RSI_THRESH = 52             # sänkt
STOP_FIXED_PCT  = 8.0
STOP_TRAIL_PCT  = 12.0
ATR_MULT        = 3.0
BASE_CAPITAL = 10000
FEE_PCT_EACH_SIDE = 0.0

def ema(s,span): return s.ewm(span=span, adjust=False).mean()
def macd(s):
    line = ema(s,12)-ema(s,26); sig=ema(line,9); hist=line-sig; return line,sig,hist
def rsi(s,period=14):
    d=s.diff(); up=d.clip(lower=0); dn=(-d).clip(lower=0)
    au=up.ewm(alpha=1/period, adjust=False).mean()
    ad=dn.ewm(alpha=1/period, adjust=False).mean()
    rs=au/ad.replace(0,np.nan); return 100-(100/(1+rs))
def atr(df,period=14):
    h,l,c=df["High"],df["Low"],df["Close"]; pc=c.shift(1)
    tr=pd.concat([(h-l),(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    return tr.rolling(period).mean()

df = yf.download(TICKER, start="2021-01-01", progress=False, auto_adjust=False).dropna()
df = df[df.index>=pd.to_datetime(START)].copy()
if df.empty: raise SystemExit("Ingen data hämtad.")

close=df["Close"]
macd_line,macd_sig,macd_hist=macd(close)
rsi14=rsi(close,14)
sma200=close.rolling(200).mean()
atr14=atr(df,14)

cross_up=(macd_line>macd_sig)&(macd_line.shift(1)<=macd_sig.shift(1))
cross_dn=(macd_line<macd_sig)&(macd_line.shift(1)>=macd_sig.shift(1))

trend_ok   =(close>sma200)                       # lättare trend
momentum_ok=(rsi14>RSI_THRESH)&(macd_hist>0)     # lättare momentum
buy_s=(cross_up & trend_ok & momentum_ok).fillna(False)
sell_s = cross_dn.fillna(False)

# 1D-arrayer
open_v=np.asarray(df["Open"].values,float).reshape(-1)
high_v=np.asarray(df["High"].values,float).reshape(-1)
low_v =np.asarray(df["Low"].values,float).reshape(-1)
dates=np.asarray(df.index.to_pydatetime()).reshape(-1)
atr_v=np.asarray(atr14.values,float).reshape(-1)
buy_v=np.asarray(buy_s.values,bool).reshape(-1)
sell_v=np.asarray(sell_s.values,bool).reshape(-1)

parts=[]; trades=[]; curve=[]
in_pos=False; qty=0; entry_px=0.0; entry_date=None
high_water=None; fixed_stop=None
exit_next=False; reason=""
initial_capital=None; capital=None

N=len(open_v)
for i in range(N-1):
    # exit på nästa öppning
    if in_pos and exit_next:
        px=float(open_v[i+1]); parts.append(f"{dates[i+1].date()} SÄLJ {qty} st @ {px:.2f}")
        fee_in=entry_px*(FEE_PCT_EACH_SIDE/100.0); fee_out=px*(FEE_PCT_EACH_SIDE/100.0)
        capital += ((px-fee_out)-(entry_px+fee_in))*qty
        curve.append({"date":dates[i+1].date(),"capital":capital})
        trades.append({"entry_date":entry_date.date(),"entry_price":round(entry_px,4),
                       "exit_date":dates[i+1].date(),"exit_price":round(px,4),
                       "qty":qty,"reason":reason})
        in_pos=False; qty=0; entry_px=0.0; entry_date=None
        high_water=None; fixed_stop=None; exit_next=False; reason=""

    # stoppar intradag
    if in_pos:
        high_water=max(high_water,float(high_v[i]))
        trail=high_water*(1-STOP_TRAIL_PCT/100.0)
        chand=high_water - (0.0 if np.isnan(atr_v[i]) else atr_v[i])*ATR_MULT
        stop_lvl=max(fixed_stop,trail,chand)
        if float(low_v[i])<=stop_lvl:
            px=float(stop_lvl); parts.append(f"{dates[i].date()} SÄLJ {qty} st @ {px:.2f}")
            fee_in=entry_px*(FEE_PCT_EACH_SIDE/100.0); fee_out=px*(FEE_PCT_EACH_SIDE/100.0)
            capital += ((px-fee_out)-(entry_px+fee_in))*qty
            curve.append({"date":dates[i].date(),"capital":capital})
            trades.append({"entry_date":entry_date.date(),"entry_price":round(entry_px,4),
                           "exit_date":dates[i].date(),"exit_price":round(px,4),
                           "qty":qty,"reason":"STOP"})
            in_pos=False; qty=0; entry_px=0.0; entry_date=None
            high_water=None; fixed_stop=None
            continue

    # entry nästa öppning
    if (not in_pos) and buy_v[i]:
        n_open=float(open_v[i+1]); q=int(BASE_CAPITAL//n_open)
        if q>0:
            qty=q; entry_px=n_open; entry_date=dates[i+1]; in_pos=True
            high_water=entry_px; fixed_stop=entry_px*(1-STOP_FIXED_PCT/100.0)
            parts.append(f"{dates[i+1].date()} KÖP {qty} st @ {entry_px:.2f}")
            if initial_capital is None:
                initial_capital=qty*entry_px; capital=initial_capital

    if in_pos and sell_v[i]:
        exit_next=True; reason="SIGNAL"

line=" ".join(parts)
if capital is not None: line += f" Slutligt kapital: {capital:.2f}"
print(line)

# summering
if trades:
    tdf=pd.DataFrame(trades)
    tdf["net_return_pct"]=np.round((tdf["exit_price"]/tdf["entry_price"]-1)*100,3)
    wins=int((tdf["net_return_pct"]>0).sum())
    print("\n--- Summering (snällare filter + stop) ---")
    print(f"Antal affärer: {len(tdf)} | Träff%: {wins/len(tdf)*100:.1f}%")
    print(f"Bästa: {tdf['net_return_pct'].max():.2f}% | Sämsta: {tdf['net_return_pct'].min():.2f}% | Snitt: {tdf['net_return_pct'].mean():.2f}%")
    if initial_capital is not None: print(f"Startkapital (infererat): {initial_capital:.2f}")
    if capital is not None: print(f"Slutligt kapital (realiserat): {capital:.2f}")
else:
    print("\n(Inga affärer även med snällare filter.)")

# spara csv
out="/app/output"; import os; os.makedirs(out, exist_ok=True)
tdf.to_csv(f"{out}/NANEXA_trades_relaxed.csv", index=False) if trades else None
pd.DataFrame(curve).to_csv(f"{out}/NANEXA_curve_relaxed.csv", index=False) if curve else None
