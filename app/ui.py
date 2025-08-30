import streamlit as st
import pandas as pd
import numpy as np
import altair as alt

from app.data import get_data
from app.strategy import build_signals
from app.backtest import run_backtest

# ---------- Page setup ----------
st.set_page_config(
    page_title="Backtest – RSI + Stops",
    layout="wide",
    initial_sidebar_state="expanded"   # öppna sidopanelen från start
)
st.title("📈 Backtest – RSI + Stops")
st.caption("UI build: 2025-08-31 10:40 – toggle+debug")

# ---------- Sidebar ----------
with st.sidebar:
    st.header("⚙️ Inställningar")
    st.markdown("**[DBG] Sidebar laddad** ✅")  # debug-markör

    # Data
    st.subheader("Data")
    ticker   = st.text_input("Ticker", "AAPL", key="w_ticker")
    start    = st.date_input("Startdatum", pd.to_datetime("2018-01-01"), key="w_start")
    interval = st.selectbox("Intervall", ["1d", "1h", "1wk"], index=0, key="w_interval")
    source   = st.selectbox("Datakälla", ["stooq", "yahoo", "auto"], index=0, key="w_source")

    # Strategi
    st.subheader("Strategi (RSI)")
    rsi_len  = st.slider("RSI-längd", 5, 30, 14, 1, key="w_rsi_len")
    rsi_buy  = st.slider("RSI – köp under", 0, 50, 52, 1, key="w_rsi_buy")
    rsi_sell = st.slider("RSI – sälj över", 50, 100, 59, 1, key="w_rsi_sell")

    # Filter
    st.subheader("Filter (valbara)")
    trend_on = st.toggle("Trendfilter (pris > SMA200)", value=False, key="w_trend")
    atr_on   = st.toggle("ATR-filter (volatilitet inom spann)", value=False, key="w_atr")
    atr_lo   = st.slider("Min ATR% av Close", 0.0, 10.0, 0.5, 0.1, key="w_atr_lo", disabled=not atr_on)
    atr_hi   = st.slider("Max ATR% av Close", 0.0, 10.0, 4.0, 0.1, key="w_atr_hi", disabled=not atr_on)

    # Stops / Targets
    st.subheader("Stops/Targets (valbara)")
    stop_on  = st.toggle("Aktivera fast stop-loss", value=True, key="w_stop_on")
    stop     = st.slider("Stop-loss (%)", 1, 10, 2, 1, key="w_stop", disabled=not stop_on)

    tp_on    = st.toggle("Aktivera take-profit", value=False, key="w_tp_on")
    tp       = st.slider("Take-profit (%)", 1, 20, 10, 1, key="w_tp", disabled=not tp_on)

    trail_on = st.toggle("Aktivera trailing stop", value=False, key="w_trail_on")
    trail    = st.slider("Trailing stop (%)", 1, 20, 8, 1, key="w_trail", disabled=not trail_on)

    tstop_on = st.toggle("Aktivera tids-stopp (bars)", value=False, key="w_tstop_on")
    tstop    = st.slider("Max bars i trade", 5, 60, 30, 1, key="w_tstop", disabled=not tstop_on)

    # Kostnader
    st.subheader("Kostnader")
    fee  = st.number_input("Courtage % per sida", 0.0, 1.0, 0.00, 0.01, key="w_fee")
    slip = st.number_input("Slippage (bps)", 0, 200, 0, 1, key="w_slip")

    # Kör
    run = st.button("🚀 Kör backtest", key="w_run")

# ---------- Debug i huvudpanelen ----------
with st.expander("🔧 Debug: Widget-state"):
    debug_state = {
        "ticker": ticker, "start": str(start), "interval": interval, "source": source,
        "rsi_len": rsi_len, "rsi_buy": rsi_buy, "rsi_sell": rsi_sell,
        "trend_on": trend_on,
        "atr_on": atr_on, "atr_lo": atr_lo, "atr_hi": atr_hi,
        "stop_on": stop_on, "stop": stop if stop_on else 0,
        "tp_on": tp_on, "tp": tp if tp_on else 0,
        "trail_on": trail_on, "trail": trail if trail_on else 0,
        "tstop_on": tstop_on, "tstop": tstop if tstop_on else 0,
        "fee_pct": fee, "slippage_bps": slip,
    }
    st.code(debug_state, language="python")

# ---------- Körning ----------
if run:
    try:
        with st.status("Hämtar data…", expanded=False):
            df = get_data(ticker, str(start), interval=interval, source=source)
            st.write(f"📊 Rader hämtade: **{len(df)}**")
            if df.empty:
                st.error("Tomt dataram. Kontrollera ticker, datum och intervall.")
                st.stop()

        with st.status("Bygger signaler…", expanded=False):
            sig = build_signals(
                df,
                rsi_buy=rsi_buy,
                rsi_sell=rsi_sell,
                rsi_len=rsi_len,
                use_trend=trend_on,
                use_atr=atr_on,
                atr_lo=atr_lo if atr_on else 0.0,
                atr_hi=atr_hi if atr_on else 999.0,
            )
            st.write("✅ Signaler byggda. Kolumner:", list(sig.columns))

        with st.status("Kör backtest…", expanded=False):
            stop_pct  = float(stop)  if stop_on  else 0.0
            tp_pct    = float(tp)    if tp_on    else 0.0
            trail_pct = float(trail) if trail_on else 0.0
            time_stop = int(tstop)   if tstop_on else 0

            st.write(f"[DBG] stop={stop_pct} tp={tp_pct} trail={trail_pct} time_stop={time_stop}")
            res = run_backtest(
                sig,
                fee_pct=fee,
                slippage_bps=slip,
                stop_pct=stop_pct,
                tp_pct=tp_pct,
                trail_pct=trail_pct,
                time_stop=time_stop,
            )
            st.write("✅ Backtest klart. Stats:", res["stats"])

        # ---- Pris + signaler ----
        plot_df = sig.reset_index().rename(columns={"index": "Date"})
        plot_df["BuyPrice"]  = np.where(plot_df["BUY"],  plot_df["Close"], np.nan)
        plot_df["SellPrice"] = np.where(plot_df["SELL"], plot_df["Close"], np.nan)

        price_line = alt.Chart(plot_df).mark_line().encode(
            x="Date:T",
            y=alt.Y("Close:Q", title="Pris"),
            tooltip=[alt.Tooltip("Date:T"), alt.Tooltip("Close:Q", format=".2f")]
        )
        buy_pts = alt.Chart(plot_df).mark_point(filled=True, size=80, color="green").encode(
            x="Date:T", y="BuyPrice:Q", tooltip=["Date:T","Close:Q"]
        )
        sell_pts = alt.Chart(plot_df).mark_point(filled=True, size=80, color="red").encode(
            x="Date:T", y="SellPrice:Q", tooltip=["Date:T","Close:Q"]
        )

        st.subheader("Pris + signaler")
        st.altair_chart(price_line + buy_pts + sell_pts, use_container_width=True)

        # ---- RSI-graf ----
        rsi_df = sig.reset_index().rename(columns={"index": "Date"})
        rsi_line = alt.Chart(rsi_df).mark_line().encode(
            x="Date:T", y=alt.Y("RSI:Q", title="RSI")
        )
        band_buy  = alt.Chart(pd.DataFrame({"y":[rsi_buy]})).mark_rule(color="green").encode(y="y:Q")
        band_sell = alt.Chart(pd.DataFrame({"y":[rsi_sell]})).mark_rule(color="red").encode(y="y:Q")

        st.subheader("RSI + trösklar")
        st.altair_chart(rsi_line + band_buy + band_sell, use_container_width=True)

        # ---- Nyckeltal ----
        s = res["stats"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Trades", s["trades"])
        c2.metric("PF", f"{s['profit_factor']:.2f}" if s['profit_factor']==s['profit_factor'] else "—")
        c3.metric("Winrate", f"{s['winrate_pct']:.1f}%")
        c1.metric("Total", f"{s['total_return_pct']:.2f}%")
        c2.metric("CAGR", f"{s['cagr_pct']:.2f}%")
        c3.metric("Max DD", f"{s['max_drawdown_pct']:.2f}%")
        st.metric("Expectancy/trade", f"{s['expectancy_pct_per_trade']:.2f}%")

        # ---- Kapitalkurva ----
        st.subheader("Kapitalkurva")
        st.line_chart(res["equity"], height=300)

        # ---- Affärer ----
        st.subheader("Affärer (entry/exit)")
        trades = res["trades"]
        if trades.empty:
            st.info("Inga trades i vald period/parametrar.")
        else:
            st.dataframe(trades, use_container_width=True)
            csv = trades.to_csv(index=False).encode("utf-8")
            st.download_button("Ladda ned affärer (CSV)", data=csv,
                               file_name="trades.csv", mime="text/csv")

    except Exception as e:
        st.error(f"Fel: {e}")
else:
    st.info("Välj parametrar i **sidopanelen** och klicka **🚀 Kör backtest**.")
