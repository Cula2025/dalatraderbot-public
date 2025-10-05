from __future__ import annotations
import json, re
from pathlib import Path
from datetime import date
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

# --- Samma dataväg som Backtest MIN ---
GET = None           # app.data_providers.get_ohlcv (Börsdata)
RUN_WRAP = None      # app.btwrap.run_backtest (om finns)
RUN_RAW  = None      # backtest.run_backtest (fallback)

try:
    from app.data_providers import get_ohlcv as GET
except Exception as e:
    st.error(f"Kunde inte importera app.data_providers.get_ohlcv: {type(e).__name__}: {e}")

try:
    from app.btwrap import run_backtest as RUN_WRAP
except Exception:
    RUN_WRAP = None

try:
    from backtest import run_backtest as RUN_RAW
except Exception:
    RUN_RAW = None

st.set_page_config(page_title="Dala Trader – Portfolio (Profiler)", page_icon="🧺", layout="wide")
st.title("🧺 Portfolio – Profiler")

# ---------- Profilhantering ----------
PROF_DIR = Path("/srv/trader/app/profiles") if Path("/srv/trader/app/profiles").exists() else Path("profiles")

def read_profiles() -> Tuple[List[str], Dict[str, List[dict]]]:
    """Läs alla profiler från profiles/*.json och returnera (tickers, map[ticker->list[profile]])"""
    tickers: List[str] = []
    pmap: Dict[str, List[dict]] = {}
    if not PROF_DIR.exists():
        return tickers, pmap
    files = sorted(PROF_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            arr = data.get("profiles", [])
            if not isinstance(arr, list): 
                continue
            for prof in arr:
                if not isinstance(prof, dict):
                    continue
                t = prof.get("ticker") or prof.get("Ticker") or ""
                t = str(t).strip()
                if not t:
                    continue
                pmap.setdefault(t, []).append(prof)
        except Exception:
            # håll robust – bara hoppa över trasiga filer
            continue
    tickers = sorted(pmap.keys())
    return tickers, pmap

def pick_profile(profs: List[dict], flavor: str) -> Optional[dict]:
    """Välj profil efter flavor: conservative/balanced/aggressive, case-insensitive."""
    if not profs:
        return None
    f = flavor.lower()
    # träffa på namn
    for p in profs:
        n = str(p.get("name","")).lower()
        if f in n:
            return p
    # fallback: försök index 0/1/2 enligt ordning (conservative/balanced/aggressive)
    idx = {"conservative":0, "balanced":1, "aggressive":2}.get(f, 0)
    if 0 <= idx < len(profs):
        return profs[idx]
    return profs[0]

# ---------- Hjälpare för BH/kurvor ----------
def _ensure_close_series(df: pd.DataFrame) -> Optional[pd.Series]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    for c in ["Adj Close","adj_close","Close","close","c"]:
        if c in df.columns:
            s = pd.to_numeric(df[c], errors="coerce").dropna()
            if not s.empty:
                s.index = pd.to_datetime(df.index)
                s = s.sort_index()
                return s
    # OHLC?
    if all(x in df.columns for x in ("open","high","low","close")):
        s = pd.to_numeric(df["close"], errors="coerce").dropna()
        if not s.empty:
            s.index = pd.to_datetime(df.index)
            return s.sort_index()
    if all(x in df.columns for x in ("Open","High","Low","Close")):
        s = pd.to_numeric(df["Close"], errors="coerce").dropna()
        if not s.empty:
            s.index = pd.to_datetime(df.index)
            return s.sort_index()
    return None

def buyhold_equity_from_price(s: pd.Series) -> pd.Series:
    s = s.astype(float).dropna().sort_index()
    eq = s / float(s.iloc[0])
    eq.name = "Buy&Hold"
    return eq

def _series_from_result(res: dict) -> Optional[pd.Series]:
    """Plocka ut equity-serie ur bt-resultat (olika fältnamn tolereras)."""
    if not isinstance(res, dict):
        return None
    cand = res.get("equity") or res.get("equity_curve") or res.get("portfolio") or res.get("balance") or res.get("cumret")
    if cand is None:
        return None
    try:
        if isinstance(cand, dict):
            s = pd.Series(cand)
        elif isinstance(cand, list) and cand and isinstance(cand[0], dict):
            kd = next((k for k in ["date","Date","ts","timestamp"] if k in cand[0]), None)
            kv = next((k for k in ["equity","value","val","y","close","Close"] if k in cand[0]), None)
            if kd and kv:
                idx = pd.to_datetime([x[kd] for x in cand])
                vals = [x[kv] for x in cand]
                s = pd.Series(vals, index=idx)
            else:
                s = pd.Series(cand)
        else:
            s = pd.Series(cand)
        s = pd.to_numeric(s, errors="coerce").dropna().sort_index()
        if len(s)>0 and float(s.iloc[0])!=0.0:
            s = s / float(s.iloc[0])
        return s.rename("Strategy")
    except Exception:
        return None

def run_strategy_or_bh(ticker: str, p: dict) -> Tuple[pd.Series, pd.Series]:
    """För en ticker: försök strategi via RUN_WRAP/RUN_RAW; fallback BH; return (equity_strategy_or_bh, bh_always)"""
    # Hämta data (behövs för BH och ev. RUN_RAW)
    if GET is None:
        raise RuntimeError("Ingen dataladdare (GET) tillgänglig.")
    try:
        df = GET(ticker, start=p.get("from_date"), end=p.get("to_date"))
    except TypeError:
        df = GET(ticker, p.get("from_date"), p.get("to_date"))
    s_close = _ensure_close_series(df)
    if s_close is None or s_close.empty:
        raise ValueError(f"Börsdata returnerade ingen Close-serie för {ticker}.")
    bh = buyhold_equity_from_price(s_close).rename(f"{ticker} · B&H")

    # Försök btwrap
    if RUN_WRAP is not None:
        try:
            res = RUN_WRAP(p={"ticker": ticker, "params": dict(p)})
            s = _series_from_result(res)
            if s is not None and not s.empty:
                return s.rename(f"{ticker} · Strat"), bh
        except Exception:
            try:
                res = RUN_WRAP(ticker, dict(p))
                s = _series_from_result(res)
                if s is not None and not s.empty:
                    return s.rename(f"{ticker} · Strat"), bh
            except Exception:
                pass

    # Fallback raw-backtest om finns
    if RUN_RAW is not None:
        try:
            res = RUN_RAW(df, dict(p))
            s = _series_from_result(res if isinstance(res, dict) else {"equity": res})
            if s is not None and not s.empty:
                return s.rename(f"{ticker} · Strat"), bh
        except Exception:
            pass

    # Sista utväg: endast BH
    return bh.rename(f"{ticker} · B&H"), bh

# ---------- UI ----------
st.caption("Läser universum från **profiles/**. Använder Börsdata via samma loader som Backtest MIN. Ingen CSV.")

tickers_all, prof_map = read_profiles()

with st.sidebar:
    st.header("Universum & period")
    use_auto_universe = st.checkbox("Använd alla tickers i profilkatalogen", value=True)
    custom = st.multiselect("Eller välj manuellt", options=tickers_all, default=tickers_all, disabled=use_auto_universe)
    sel = tickers_all if use_auto_universe else custom

    flavor = st.radio("Profil-variant", ["conservative","balanced","aggressive"], index=1, horizontal=True)

    # Period (hämtas in i prof-parametrar)
    from_date = st.text_input("Från (YYYY-MM-DD)", value="2020-10-01")
    to_date   = st.text_input("Till (YYYY-MM-DD)",  value=date.today().isoformat())

    st.markdown("---")
    go = st.button("🚀 Bygg portfölj", type="primary", use_container_width=True)

if not sel:
    st.info("Ingen ticker hittad – lägg till profiler i `profiles/` eller avmarkera auto-universum.")
    st.stop()

# ---------- Körning ----------
if go:
    curves: Dict[str, pd.Series] = {}
    bh_curves: Dict[str, pd.Series] = {}

    for t in sel:
        profs = prof_map.get(t, [])
        prof  = pick_profile(profs, flavor) or {}
        params = dict(prof.get("params", {}))
        # tvinga period från UI att gälla (Backtest MIN gör liknande)
        params["from_date"] = from_date
        params["to_date"]   = to_date

        try:
            strat, bh = run_strategy_or_bh(t, params)
            curves[t]   = strat
            bh_curves[t]= bh
        except Exception as e:
            st.warning(f"{t}: {e}")

    if not curves:
        st.error("Hittade inga kurvor att rita (Börsdata eller motor returnerade inget).")
        st.stop()

    # Align & equal-weight
    idx = sorted(set().union(*[s.index for s in curves.values()]))
    dfS = pd.DataFrame({k: v.reindex(idx).ffill() for k,v in curves.items()}).dropna(how="all")
    dfB = pd.DataFrame({k: v.reindex(idx).ffill() for k,v in bh_curves.items()}).dropna(how="all")

    # Normalisera & EW
    if not dfS.empty:
        portS = dfS.mean(axis=1).rename("Portfölj · Strat")
    else:
        portS = None
    if not dfB.empty:
        portB = dfB.mean(axis=1).rename("Portfölj · B&H")
    else:
        portB = None

    st.markdown("### Kurvor")
    # Portfolio först
    if portS is not None:
        st.line_chart(portS, width='stretch', height=300)
    if portB is not None:
        st.line_chart(portB, width='stretch', height=300)

    # Enskilda (kort)
    with st.expander("Visa enskilda tickers"):
        if not dfS.empty:
            st.line_chart(dfS, width='stretch', height=300)
        if not dfB.empty:
            st.line_chart(dfB, width='stretch', height=300)

else:
    st.info("Välj universum och klicka **🚀 Bygg portfölj**.")
