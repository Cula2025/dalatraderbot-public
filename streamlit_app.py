import streamlit as st
import subprocess, sys, os

st.set_page_config(page_title="Dalatraderbot", layout="wide")
st.title("Dalatraderbot ✅")

# ---- Basform (behåll om du vill) ----
defaults = {"ticker":"AAPL","period":"6mo","interval":"1d","fast":10,"slow":20}
for k,v in defaults.items():
    st.session_state.setdefault(k,v)

with st.form("inputs"):
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Ticker", key="ticker")
        st.selectbox("Period", ["3mo","6mo","1y","2y"], key="period")
        st.number_input("Snabb SMA", 3, 100, key="fast")
    with col2:
        st.selectbox("Intervall", ["1d","1h","1wk"], key="interval")
        st.number_input("Långsam SMA", 5, 300, key="slow")
    go = st.form_submit_button("Kör")

if go:
    st.success(
        f"Input mottaget. Ticker={st.session_state['ticker']}, "
        f"period={st.session_state['period']}, intervall={st.session_state['interval']}"
    )

# ---- Helper: kör modul och visa stdout/stderr ----
def run_module(mod_name: str, *args: str):
    cmd = [sys.executable, "-m", mod_name, *args]
    st.write("Kör:", " ".join(cmd))
    with st.spinner("Kör…"):
        proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    st.code(out.strip() or "(ingen output)")
    if proc.returncode == 0:
        st.success("Klart")
    else:
        st.error(f"Avslutades med kod {proc.returncode}")

# ---- Flikar för skripten i app/ ----
tab1, tab2, tab3 = st.tabs(["trading_bot", "alert_bot", "alert_batch"])

with tab1:
    st.caption("Kör `app/trading_bot.py`")
    if st.button("Starta trading_bot"):
        run_module("app.trading_bot")

with tab2:
    st.caption("Kör `app/alert_bot.py`")
    if st.button("Starta alert_bot"):
        run_module("app.alert_bot")

with tab3:
    st.caption("Kör `app/alert_batch.py`")
    if st.button("Kör alert_batch"):
        run_module("app.alert_batch")

# ---- (valfritt) visa om hemligheter finns (utan att skriva ut dem) ----
has_token = bool(os.getenv("TELEGRAM_TOKEN") or st.secrets.get("TELEGRAM_TOKEN", ""))
if has_token:
    st.caption("🔐 Telegram-token hittad via env/secrets.")

