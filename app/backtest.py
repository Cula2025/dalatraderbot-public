# app/backtest.py
import argparse
from dataclasses import dataclass
from datetime import datetime, date
import math
import sys
import numpy as np
import pandas as pd
import yfinance as yf

@dataclass
class Params:
    ticker: str = "AAPL"
    start: str = "2018-01-01"   # YYYY-MM-DD
    interval: str = "1d"        # 1d, 1h, 1wk
    source: str = "stooq"       # används ej – vi hämtar via yfinance oavsett
    rsi_buy: int = 52           # köp när RSI <= detta
    rsi_sell: int = 59          # sälj när RSI >= detta
    use_sl: bool = True
    sl: float = 2.0             # stop-loss i %
    fee: float = 0.00           # courtage per sida (0.001 = 0.1%)
    slip_bps: int = 0           # slippage i bps (10 = 0.10%)

def _to_date(s: str) -> datetime:
    if isinstance(s, date):
        return datetime(s.year, s.month, s.day)
    return datetime.fromisoformat(str(s))

def load_prices(ticker: str, start: str, interval: str) -> pd.DataFrame:
    df = yf.download(ticker, start=_to_date(start), interval=interval, auto_adjust=True, progress=False, threads=False)
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(0, axis=1)
    return df.dropna()

def rsi_series(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean().replace(0, np.nan)
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(method="bfill").fillna(50.0)

def backtest_rsi(df: pd.DataFrame, p: Params) -> dict:
    if df.empty or "Close" not in df.columns:
        raise ValueError("Tom data – kunde inte hämta priser.")
    close = df["Close"].copy()
    rsi = rsi_series(close, 14)

    slip = p.slip_bps / 10_000.0
    fee = p.fee
    sl_mult = 1.0 - (p.sl / 100.0)

    equity = 1.0
    eq_curve = [equity]
    in_pos = False
    entry_price = np.nan

    trades = []
    wins = 0

    dates = close.index
    for i in range(1, len(dates)):
        today = dates[i]
        prev = dates[i - 1]
        price = float(close.loc[today])
        price_prev = float(close.loc[prev])
        r = float(rsi.loc[today])

        # mark-to-market om vi är i position
        if in_pos:
            # dagsavkastning i priset
            growth = price / price_prev if price_prev > 0 else 1.0
            equity *= growth

        # sälj villkor
        sell_now = False
        if in_pos:
            stop_price = entry_price * sl_mult if p.use_sl else -math.inf
            if (p.use_sl and price <= stop_price) or (r >= p.rsi_sell):
                sell_now = True

        # köp villkor
        buy_now = False
        if not in_pos and (r <= p.rsi_buy):
            buy_now = True

        # genomför affärer (kostnader appliceras som multiplikatorer)
        if sell_now:
            # slippage + courtage vid exit
            equity *= (1.0 - slip) * (1.0 - fee)
            # trade-resultat
            trade_ret = price / entry_price * (1.0 - slip) * (1.0 - fee)  # inkl kostnader
            wins += 1 if trade_ret > 1.0 else 0
            trades.append(trade_ret)
            in_pos = False
            entry_price = np.nan

        if buy_now:
            # slippage + courtage vid entry
            equity *= (1.0 - slip) * (1.0 - fee)
            entry_price = price
            in_pos = True

        eq_curve.append(equity)

    eq = pd.Series(eq_curve, index=dates)
    max_equity = eq.cummax()
    dd = (eq / max_equity - 1.0)
    max_dd = dd.min() if len(dd) else 0.0

    start_dt = dates[0].to_pydatetime()
    end_dt = dates[-1].to_pydatetime()
    years = max((end_dt - start_dt).days / 365.25, 1e-9)
    total_ret = eq.iloc[-1] - 1.0
    cagr = (eq.iloc[-1]) ** (1 / years) - 1.0 if eq.iloc[-1] > 0 else -1.0

    summary = {
        "ticker": p.ticker,
        "from": start_dt.date().isoformat(),
        "to": end_dt.date().isoformat(),
        "bars": int(len(df)),
        "trades": int(len(trades)),
        "win_rate": (wins / len(trades)) if trades else 0.0,
        "total_return_pct": total_ret * 100.0,
        "cagr_pct": cagr * 100.0,
        "max_drawdown_pct": max_dd * 100.0,
        "final_equity": float(eq.iloc[-1]),
    }
    return summary

def run(
    ticker: str = "AAPL",
    start: str = "2018-01-01",
    interval: str = "1d",
    source: str = "stooq",
    rsi_buy: int = 52,
    rsi_sell: int = 59,
    use_sl: bool = True,
    sl: float = 2.0,
    fee: float = 0.00,
    slip_bps: int = 0,
):
    p = Params(
        ticker=ticker,
        start=start,
        interval=interval,
        source=source,
        rsi_buy=int(rsi_buy),
        rsi_sell=int(rsi_sell),
        use_sl=bool(int(use_sl)) if isinstance(use_sl, (str, int)) else bool(use_sl),
        sl=float(sl),
        fee=float(fee),
        slip_bps=int(slip_bps),
    )
    df = load_prices(p.ticker, p.start, p.interval)
    summary = backtest_rsi(df, p)

    # skriv trevliga rader (Streamlit visar stdout i en kodruta)
    print(f"Backtest {summary['ticker']} {summary['from']} → {summary['to']}  ({summary['bars']} barer)")
    print(f"Affärer: {summary['trades']}, Win-rate: {summary['win_rate']*100:.1f}%")
    print(f"Total avkastning: {summary['total_return_pct']:.2f}%")
    print(f"CAGR: {summary['cagr_pct']:.2f}%   Max DD: {summary['max_drawdown_pct']:.2f}%")
    print(f"Slutligt kapital (start=1.00): {summary['final_equity']:.4f}")
    return summary

def main(argv=None):
    parser = argparse.ArgumentParser(description="RSI backtest (enkel)")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--source", default="stooq")
    parser.add_argument("--rsi-buy", type=int, default=52)
    parser.add_argument("--rsi-sell", type=int, default=59)
    parser.add_argument("--use-sl", type=int, default=1)  # 1/0
    parser.add_argument("--sl", type=float, default=2.0)
    parser.add_argument("--fee", type=float, default=0.00)
    parser.add_argument("--slip-bps", type=int, default=0)
    args = parser.parse_args(argv)

    run(
        ticker=args.ticker,
        start=args.start,
        interval=args.interval,
        source=args.source,
        rsi_buy=args.rsi_buy,
        rsi_sell=args.rsi_sell,
        use_sl=bool(args.use_sl),
        sl=args.sl,
        fee=args.fee,
        slip_bps=args.slip_bps,
    )

if __name__ == "__main__":
    main()

