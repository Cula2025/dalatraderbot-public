import streamlit as st
import sys, subprocess, shlex, importlib, inspect
from datetime import date

st.set_page_config(page_title="Dalatraderbot", layout="wide")
st.title("Dalatraderbot ✅")

# ---------- STATE (initiera EN gång) ----------
defaults = {
    "ticker": "AAPL",
    "start_date": date(2018, 1, 1),
    "interval": "1d",
    "source": "stooq",
    "rsi_buy": 52,      # "RSI – köp under" (0–52)
    "rsi_sell": 59,     # "RSI – sälj över" (50–100)
    "use_sl": True,     # aktivera stop-loss
    "sl_pct": 2,        # 1–10 (%)
    "fee_pct": 0.00,    # courtage % per sida
    "slip_bps": 0,      # slippage i bps
}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# ---------- Hjälpare ----------
def run_backtest(params: dict):
    """
    Försök 1: Python-API (app/backtest.py med en av funktionerna run/main/backtest/execute)
    Försök 2: Subprocess (python -m app.backtest --flaggor ...)
    """
    # --- Försök 1: direkt import ---
    try:
        mod = importlib.import_module("app.backtest")
        for fn_name in ("run", "main", "backtest", "execute"):
            if hasattr(mod, fn_name):
                fn = getattr(mod, fn_name)
                # Skicka bara parametrar som funktionen faktiskt accepterar
                sig = inspect.signature(fn)
                allowed = {k: v for k, v in params.items() if k in sig.parameters}
                with st.spinner(f"Kör Python-API: backtest.{fn_name}(...)"):
                    res = fn(**allowed)  # type: ignore[arg-type]
                st.success("Backtest klart via Python-API.")
                if res is not None:
                    st.write(res)
                return
        st.info("Hittade ingen körbar funktion i app/backtest.py (run/main/backtest/execute). Provar subprocess…")
    except Exception as e:
        st.info(f"Python-API misslyckades ({e}). Provar subprocess…")

    # --- Försök 2: subprocess/CLI ---
    args = []
    # Skicka med vanliga flaggor – anpassa efter vad ditt skript stödjer
    mapping = {
        "ticker": "ticker",
        "start_date": "start",
        "interval": "interval",
        "source": "source",
        "rsi_buy": "rsi-buy",
        "rsi_sell": "rsi-sell",
        "use_sl": "use-sl",
        "sl_pct": "sl",
        "fee_pct": "fee",
        "slip_bps": "slip-bps",
    }
    for k, flag in mapping.items():
        val = params[k]
        # konvertera datum till YYYY-MM-DD
        if hasattr(val, "isoformat"):
            val = val.isoformat()
        # bool hanteras som 1/0 för CLI
        if isinstance(val, bool):
            val = "1" if val else "0"
        args += [f"--{flag}", str(val)]

    cmd = [sys.executable, "-m", "app.backtest", *args]
    st.write("Kör:", " ".join(cmd))
    with st.spinner("Kör subprocess…"):
        proc = subprocess.run(cmd, capture_output=True, text=True)
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    st.code(output.strip() or "(ingen output)")
    if proc.returncode == 0:
        st.success("Backtest klart.")
    else:
        st.error(f"Avslutades med kod {proc.returncode}")

# ---------- LAYOUT ----------
left, right = st.columns([1, 1])

with left:
    st.header("Data")
    st.text_input("Ticker", key="ticker")
    st.date_input("Startdatum", key="start_date")  # default via state
    st.selectbox("Intervall", ["1d", "1h", "1wk"], key="interval")
    st.selectbox("Datakälla", ["stooq", "yfinance"], key="source")

    st.header("Strategi")
    # RSI – köp under (0–52)
    st.slider("RSI – köp under", min_value=0, max_value=52, key="rsi_buy")
    # RSI – sälj över (50–100)
    st.slider("RSI – sälj över", min_value=50, max_value=100, key="rsi_sell")

with right:
    st.header("Stop-loss")
    st.checkbox("Aktivera stop-loss", key="use_sl")
    st.slider("Stop-loss (%)", min_value=1, max_value=10, key="sl_pct")

    st.header("Kostnader")
    st.number_input("Courtage % per sida", min_value=0.00, max_value=2.00, step=0.01, format="%.2f", key="fee_pct")
    st.number_input("Slippage (bps)", min_value=0, max_value=1000, step=1, key="slip_bps")

    st.write("")
    if st.button("Kör backtest"):
        params = dict(st.session_state)
        run_backtest(params)

st.caption("Formen ovan matchar din backtester. Vi kör backtest via Python-API om möjligt, annars via subprocess.")
