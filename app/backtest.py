import numpy as np
import pandas as pd

def run_backtest(
    df: pd.DataFrame,
    fee_pct: float = 0.0,        # courtage per sida i %
    slippage_bps: int = 0,       # slippage i basis points (1/100 av %)
    stop_pct: float = 0.0,       # fast stop-loss i % (0 = av)
    tp_pct: float = 0.0,         # (valfritt) take-profit i % (0 = av)
    trail_pct: float = 0.0,      # (valfritt) trailing stop i % (0 = av)
    time_stop: int = 0           # (valfritt) max antal bars i trade (0 = av)
):
    """
    Enkel long-only backtest:
      - Max en position åt gången.
      - Entry: när df['BUY'] är True (på slutet av baren -> använder Close som fill).
      - Exit:  STOP (om Low når stopnivån intra-bar), TP (om High når TP), TRAIL (om Low når trailingnivå),
               SELL-signal (end-of-bar).
      - Om en trade är öppen på sista baren, stängs den på sista Close (ExitType='EOD').

    Antaganden för fills:
      - Entry på Close * (1 + slippage).
      - STOP/TRAIL på respektive nivå * (1 - slippage).
      - TP på respektive nivå * (1 - slippage) (konservativt).
      - SELL/EOD på Close * (1 - slippage).
      - Avgift (fee_pct) dras på både entry och exit.

    Returnerar:
      {
        "trades": DataFrame med Entry/Exit mm,
        "returns": list med nettoreturer per trade (decimaler),
        "equity": list med kumulativ equity (start 1.0),
        "stats": dict med nyckeltal
      }
    """
    d = df.copy()

    # Säkerställ kolumner finns
    for col in ("Open","High","Low","Close"):
        if col not in d.columns:
            raise ValueError(f"Saknar kolumn '{col}' i data.")
    for col in ("BUY","SELL"):
        if col not in d.columns:
            # Om inga signaler, skapa False-kolumner
            d[col] = False

    prices_c = d["Close"].values
    prices_h = d["High"].values
    prices_l = d["Low"].values
    index    = d.index

    in_pos = False
    entry_idx = None
    entry_px  = None
    best_px   = None       # högsta pris sedan entry (för trailing)
    bars_in   = 0          # bars i aktiv trade

    trade_rows = []
    rets = []

    slip_in  = (1 + slippage_bps/10000.0)
    slip_out = (1 - slippage_bps/10000.0)

    for i in range(len(d)):
        # ENTRY (end-of-bar)
        if (not in_pos) and bool(d.iloc[i]["BUY"]):
            in_pos = True
            entry_idx = i
            entry_px = float(prices_c[i] * slip_in)
            best_px = float(prices_c[i])
            bars_in = 0
            continue

        # EXIT-logik om i position
        if in_pos:
            exit_px = None
            exit_idx = None
            exit_type = None

            bars_in += 1
            # Uppdatera bästa pris för trailing
            best_px = max(best_px, float(prices_c[i]))

            # 1) Trailing stop (intra-bar mot Low)
            if trail_pct and trail_pct > 0:
                trail_level = best_px * (1 - trail_pct/100.0)
                if prices_l[i] <= trail_level:
                    exit_px   = float(trail_level * slip_out)
                    exit_idx  = i
                    exit_type = "TRAIL"

            # 2) Stop-loss (intra-bar mot Low) om inte redan sålt
            if (exit_px is None) and stop_pct and stop_pct > 0:
                stop_level = entry_px * (1 - stop_pct/100.0)
                # Jämför mot Low på baren
                if prices_l[i] <= stop_level:
                    exit_px   = float(stop_level * slip_out)
                    exit_idx  = i
                    exit_type = "STOP"

            # 3) Take-profit (intra-bar mot High)
            if (exit_px is None) and tp_pct and tp_pct > 0:
                tp_level = entry_px * (1 + tp_pct/100.0)
                if prices_h[i] >= tp_level:
                    exit_px   = float(tp_level * slip_out)
                    exit_idx  = i
                    exit_type = "TP"

            # 4) Time-stop (slut på baren)
            if (exit_px is None) and time_stop and time_stop > 0 and bars_in >= time_stop:
                exit_px   = float(prices_c[i] * slip_out)
                exit_idx  = i
                exit_type = "TIME"

            # 5) Sälj-signal (slut på baren)
            if (exit_px is None) and bool(d.iloc[i]["SELL"]):
                exit_px   = float(prices_c[i] * slip_out)
                exit_idx  = i
                exit_type = "SELL"

            # Om vi exitar på denna bar:
            if exit_px is not None:
                gross = (exit_px / entry_px) - 1.0
                net   = gross - (fee_pct/100.0)*2
                rets.append(float(net))

                trade_rows.append({
                    "EntryDate": index[entry_idx],
                    "EntryPrice": float(entry_px),
                    "ExitDate": index[exit_idx],
                    "ExitPrice": float(exit_px),
                    "Days": int((index[exit_idx] - index[entry_idx]).days or 0),
                    "ExitType": exit_type,
                    "Return%": float(net*100.0),
                })
                in_pos = False
                entry_idx = None
                entry_px  = None
                best_px   = None
                bars_in   = 0

    # Stäng eventuell öppen position vid sista barens close (EOD)
    if in_pos and entry_idx is not None:
        last_i = len(d) - 1
        exit_px   = float(prices_c[last_i] * slip_out)
        exit_idx  = last_i
        gross = (exit_px / entry_px) - 1.0
        net   = gross - (fee_pct/100.0)*2
        rets.append(float(net))
        trade_rows.append({
            "EntryDate": index[entry_idx],
            "EntryPrice": float(entry_px),
            "ExitDate": index[exit_idx],
            "ExitPrice": float(exit_px),
            "Days": int((index[exit_idx] - index[entry_idx]).days or 0),
            "ExitType": "EOD",
            "Return%": float(net*100.0),
        })

    # Equity-kurva
    equity = np.cumprod([1.0] + [1.0 + r for r in rets]).tolist()

    trades_df = pd.DataFrame(trade_rows)

    # Nyckeltal
    if trades_df.empty:
        wins = pd.Series(dtype=float)
        losses = pd.Series(dtype=float)
    else:
        wins = trades_df.loc[trades_df["Return%"] > 0, "Return%"]
        losses = trades_df.loc[trades_df["Return%"] <= 0, "Return%"]

    winrate = float(len(wins) / len(trades_df)) if len(trades_df) else 0.0
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    pf = (wins.sum() / abs(losses.sum())) if len(losses) and abs(losses.sum()) > 0 else np.nan

    # expectancy i % per trade (vägt med sannolikheter)
    expectancy = ((wins.mean()/100.0) if len(wins) else 0.0) * winrate + \
                 ((losses.mean()/100.0) if len(losses) else 0.0) * (1 - winrate)

    # Max drawdown på equity
    eq = np.array(equity) if equity else np.array([1.0])
    peak = np.maximum.accumulate(eq)
    dd = (eq/peak - 1.0)
    maxdd = float(dd.min()) if len(dd) else 0.0

    # CAGR
    if len(d.index) >= 2:
        days = (d.index[-1] - d.index[0]).days
        years = max(days / 365.25, 1e-9)
        total = equity[-1] if equity else 1.0
        cagr = (total ** (1/years)) - 1 if total > 0 else -1.0
    else:
        cagr = 0.0

    stats = {
        "trades": int(len(trades_df)),
        "total_return_pct": float((equity[-1]-1.0)*100 if equity else 0.0),
        "cagr_pct": float(cagr*100),
        "winrate_pct": float(winrate*100),
        "profit_factor": float(pf) if pf == pf else np.nan,
        "expectancy_pct_per_trade": float(expectancy*100),
        "max_drawdown_pct": float(maxdd*100),
        "avg_win_pct": float(avg_win),
        "avg_loss_pct": float(avg_loss),
    }

    return {"trades": trades_df, "returns": rets, "equity": equity, "stats": stats}

