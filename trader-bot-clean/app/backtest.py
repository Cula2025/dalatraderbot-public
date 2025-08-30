import numpy as np
import pandas as pd

def run_backtest(df: pd.DataFrame, fee_pct: float = 0.0, slippage_bps: int = 0):
    """
    Enkel backtestmotor: 1 position åt gången, long only.
    Exit sker när SELL triggar. (Stoppar kan läggas till senare.)
    """
    d = df.copy()
    pos = 0
    entry_px = None
    rets = []
    trades = []

    for i, row in d.iterrows():
        px = row["Close"]

        if pos == 0 and row.get("BUY", False):
            pos = 1
            entry_px = px * (1 + slippage_bps/10000)
            trades.append({"Type": "BUY", "Date": i, "Price": float(entry_px)})

        elif pos == 1 and row.get("SELL", False):
            exit_px = px * (1 - slippage_bps/10000)
            ret = (exit_px / entry_px - 1) - (fee_pct/100)*2  # courtage båda sidor
            rets.append(float(ret))
            trades.append({"Type": "SELL", "Date": i, "Price": float(exit_px), "PnL": float(ret)})
            pos = 0
            entry_px = None

    equity = np.cumprod([1.0] + [1.0 + r for r in rets])
    return {
        "trades": pd.DataFrame(trades),
        "returns": rets,
        "equity": equity.tolist()
    }
