import streamlit as st
import sys, subprocess, shlex, pkgutil

st.set_page_config(page_title="Dalatraderbot", layout="wide")
st.title("Dalatraderbot ✅")

# ---- Initiera state EN gång (utan widget-defaults som krockar) ----
defaults = {"ticker":"AAPL","period":"6mo","interval":"1d","fast":10,"slow":20}
for k,v in defaults.items():
    st.session_state.setdefault(k, v)

# ---- Hjälpare: kör modul och visa stdout/stderr ----
def run_module(mod_name: str, args_line: str = ""):
    cmd = [sys.executable, "-m", mod_name]
    if args_line.strip():
        cmd += shlex.split(args_line)
    st.write("Kör:", " ".join(cmd))
    with st.spinner("Kör…"):
        proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    st.code(out.strip() or "(ingen output)")
    if proc.returncode == 0:
        st.success("Klart")
    else:
        st.error(f"Avslutades med kod {proc.returncode}")

# ---- Upptäck backtest-moduler i app/ ----
def list_backtest_modules():
    try:
        import app  # kräver att app/__init__.py finns (du har lagt in det)
    except Exception as e:
        st.error(f"Kunde inte importera paketet 'app': {e}")
        return []
    mods = []
    for m in pkgutil.iter_modules(app.__path__):
        name = m.name
        if name == "backtest" or name.startswith("bt_"):
            mods.append(name)
    return sorted(mods)

# ---- Flikar ----
tab_bt, tab_trading, tab_alert = st.tabs(["Backtest", "trading_bot", "alert_bot"])

with tab_bt:
    st.subheader("Kör backtest-modul från `app/`")
    mods = list_backtest_modules()
    if not mods:
        st.warning("Hittade inga moduler som heter `backtest.py` eller börjar på `bt_` i `app/`.")
    else:
        st.selectbox("Välj modul", mods, key="bt_module")
        st.text_input("Valfria CLI-argument (t.ex. --ticker AAPL --days 200)", key="bt_args")
        if st.button("Kör backtest"):
            run_module(f"app.{st.session_state['bt_module']}", st.session_state["bt_args"])

with tab_trading:
    st.caption("Kör `app/trading_bot.py`")
    if st.button("Starta trading_bot"):
        run_module("app.trading_bot")

with tab_alert:
    st.caption("Kör `app/alert_bot.py`")
    if st.button("Starta alert_bot"):
        run_module("app.alert_bot")

