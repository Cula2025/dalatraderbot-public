import streamlit as st
import yfinance as yf

st.title("Minimal test – yfinance + Streamlit")
data = yf.download("AAPL", start="2023-01-01", progress=False)
st.write(data.head())
if not data.empty:
    st.line_chart(data["Close"])
else:
    st.warning("Ingen data hämtades. Testa en annan ticker eller datum.")
