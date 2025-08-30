import streamlit as st
import pandas as pd
from data import get_data
from strategy import build_signals
from backtest import run_backtest

st.set_page_config(page_title="Backtest – Clean RSI", layout="wide")
st.title("📈 Enkel Backtest – RSI (clean start)")

with st.sidebar:
    st.subheader("Data")
    ticker = st.text_input("Ticker", "AAPL")
    start = st.date_input("Startdatum", pd.to_datetime("2023-01-01"))
    interval = st.selectbox("Intervall", ["1d", "1h", "1wk"], index=0)

    st.subheader("Strategi")
    rsi_buy = st.slider("RSI – köp under", 0, 50, 45, 1)
    rsi_sell = st.slider("RSI – sälj över", 50, 100, 55, 1)

    st.subheader("Kostnader")
    fee = st.number_input("Courtage % per sida", 0.0, 1.0, 0.00, 0.01)
    slip = st.number_input("Slippage (bps)", 0, 100, 0, 1)

    run = st.button("Kör backtest")

col1, col2 = st.columns([2,1])

if run:
    try:
        with st.status("Hämtar data…", expanded=False):
            df = get_data(ticker, str(start), interval=interval)
        with st.status("Bygger signaler…", expanded=False):
            sig = build_signals(df, rsi_buy=rsi_buy, rsi_sell=rsi_sell)
        with st.status("Kör backtest…", expanded=False):
            res = run_backtest(sig, fee_pct=fee, slippage_bps=slip)

        with col1:
            st.subheader("Kapitalkurva")
            st.line_chart(res["equity"], height=300)
        with col2:
            st.subheader("Nyckeltal")
            trades = len(res["returns"])
            total_ret = (res["equity"][-1] - 1) * 100 if res["equity"] else 0.0
            st.metric("Antal trades", trades)
            st.metric("Total avkastning", f"{total_ret:.2f}%")

        st.subheader("Trades")
        if res["trades"].empty:
            st.info("Inga trades i vald period/parametrar.")
        else:
            st.dataframe(res["trades"], use_container_width=True)

        st.subheader("Data (senaste 5)")
        st.dataframe(sig.tail(), use_container_width=True)

    except Exception as e:
        st.error(f"Fel: {e}")
        st.stop()

else:
    st.info("Fyll i sidopanelen och klicka **Kör backtest**.")
