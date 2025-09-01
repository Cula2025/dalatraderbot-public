import streamlit as st

st.set_page_config(page_title="Dalatraderbot", layout="centered")
st.title("Dalatraderbot ✅")

# --- Initiera session state säkert ---
defaults = {
    "text": "",
    "ticker": "AAPL",
    "period": "6mo",
    "interval": "1d",
    "fast": 10,
    "slow": 20,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# --- Minimal testsektion (bevisar att appen kör) ---
with st.form("inputs"):
    st.text_input("Skriv något", key="text")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Ticker", key="ticker")
        st.selectbox("Period", ["3mo", "6mo", "1y", "2y"], index=["3mo","6mo","1y","2y"].index(st.session_state["period"]), key="period")
    with col2:
        st.selectbox("Intervall", ["1d", "1h", "1wk"], index=["1d","1h","1wk"].index(st.session_state["interval"]), key="interval")
        st.number_input("Snabb SMA", min_value=3, max_value=100, key="fast")
        st.number_input("Långsam SMA", min_value=5, max_value=300, key="slow")
    go = st.form_submit_button("Kör")

if go:
    st.success(f"Input mottaget. Text='{st.session_state['text']}', ticker={st.session_state['ticker']}")

st.caption("Om du ser denna sida utan fel, funkar Streamlit-appen. Vi kan koppla in din botlogik i nästa steg.")
