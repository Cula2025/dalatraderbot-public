import argparse
import itertools
from pathlib import Path
import pandas as pd

from app.data import get_data
from app.strategy import build_signals
from app.backtest import run_backtest


# -------- Helpers för att tolka intervall --------

def parse_range(spec: str):
    """
    Heltal: '30:50:2' -> [30,32,...,50]
            '45'       -> [45]
    """
    if ":" in spec:
        parts = [int(x) for x in spec.split(":")]
        if len(parts) == 3:
            a, b, s = parts
        elif len(parts) == 2:
            a, b = parts
            s = 1
        else:
            raise ValueError("Range måste vara 'start:end[:step]'")
        return list(range(a, b + 1, s))
    return [int(spec)]


def parse_range_f(spec: str):
    """
    Flyttal: '0:5:1' -> [0.0,1.0,2.0,3.0,4.0,5.0]
             '2.5'   -> [2.5]
    """
    if ":" in spec:
        a, b, s = [float(x) for x in spec.split(":")]
        vals = []
        v = a
        # robust floating-step
        while v <= b + 1e-12:
            vals.append(round(v, 10))
            v += s
        return vals
    return [float(spec)]


# -------- Core --------

def leaderboard(
    df: pd.DataFrame,
    rsi_buy_range,
    rsi_sell_range,
    sl_list,           # stop-loss %
    tp_list=None,      # take-profit %
    trail_list=None,   # trailing %
    tstop_list=None,   # time-stop (bars)
    fee_pct=0.0,
    slippage_bps=0,
    min_trades=10,
    max_dd_pct=50.0,
    min_pf=1.0,
    sort_by="cagr_pct",
):
    if tp_list is None: tp_list = [0.0]
    if trail_list is None: trail_list = [0.0]
    if tstop_list is None: tstop_list = [0]

    rows = []
    for rb, rs, sl, tp, tr, ts in itertools.product(
        rsi_buy_range, rsi_sell_range, sl_list, tp_list, trail_list, tstop_list
    ):
        if rb >= rs:
            continue

        sig = build_signals(df, rsi_buy=rb, rsi_sell=rs)
        res = run_backtest(
            sig,
            fee_pct=fee_pct,
            slippage_bps=slippage_bps,
            stop_pct=sl,
            tp_pct=tp,
            trail_pct=tr,
            time_stop=ts,
        )
        s = res["stats"]

        # filter
        if s["trades"] < min_trades:
            continue
        if s["max_drawdown_pct"] > max_dd_pct:
            continue
        pf = s["profit_factor"]
        if not (pf == pf) or pf < min_pf:
            continue

        rows.append({
            "rsi_buy": rb,
            "rsi_sell": rs,
            "sl_fast_pct": sl,
            "tp_pct": tp,
            "trail_pct": tr,
            "tstop_bars": ts,
            **s
        })

    df_lead = pd.DataFrame(rows)
    if df_lead.empty:
        return df_lead
    return df_lead.sort_values(by=sort_by, ascending=False).reset_index(drop=True)


def time_split(df: pd.DataFrame, split_date: str):
    split = pd.to_datetime(split_date)
    train = df[df.index < split]
    test = df[df.index >= split]
    return train, test


def print_best_row(df_lead: pd.DataFrame, title: str):
    print(f"\n=== {title}: bästa rad ===")
    best = df_lead.iloc[0]
    keys = [
        "rsi_buy", "rsi_sell", "sl_fast_pct", "tp_pct", "trail_pct", "tstop_bars",
        "trades", "total_return_pct", "cagr_pct", "winrate_pct",
        "profit_factor", "expectancy_pct_per_trade", "max_drawdown_pct",
        "avg_win_pct", "avg_loss_pct"
    ]
    for k in keys:
        if k in best.index:
            print(f"{k}: {best[k]}")
    return best


def main():
    ap = argparse.ArgumentParser(
        description="Optimize RSI/Stops med Train/Test och utskrift av bästa rad."
    )
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--interval", default="1d")
    ap.add_argument("--source", default="auto", choices=["auto", "yahoo", "stooq"])

    # Parametrar att svepa
    ap.add_argument("--rsi_buy", default="48:52:1")
    ap.add_argument("--rsi_sell", default="55:61:1")

    ap.add_argument("--sl_fast", default="0", help="Fast stop-loss i %, t.ex. '0' eller '0:5:1'")
    ap.add_argument("--tp", default="0", help="Take-profit i %, t.ex. '0' eller '8:12:1'")
    ap.add_argument("--trail", default="0", help="Trailing stop i %, t.ex. '0' eller '4:10:2'")
    ap.add_argument("--tstop", default="0", help="Time-stop i bars, t.ex. '0' eller '10:40:5'")

    # Kostnader
    ap.add_argument("--fee", type=float, default=0.00, help="Courtage % per sida")
    ap.add_argument("--slip", type=int, default=0, help="Slippage bps")

    # Kriterier/sortering
    ap.add_argument("--min_trades", type=int, default=20)
    ap.add_argument("--max_dd", type=float, default=30.0)
    ap.add_argument("--min_pf", type=float, default=1.2)
    ap.add_argument("--sort_by", default="cagr_pct",
                    help="t.ex. cagr_pct, total_return_pct, profit_factor, trades")

    # Train/Test
    ap.add_argument("--split", default="", help="Datum för Train/Test, ex 2023-01-01")

    # Output + utskrift
    ap.add_argument("--out", default="opt_results.csv")
    ap.add_argument("--print_best", action="store_true", help="Skriv ut bästa radens parametrar")

    args = ap.parse_args()

    # Hämta data
    df = get_data(args.ticker, args.start, interval=args.interval, source=args.source)
    print(f"Loaded {len(df)} rows for {args.ticker} [{args.source}] {args.interval} since {args.start}")

    rb = parse_range(args.rsi_buy)
    rs = parse_range(args.rsi_sell)
    sl_list = parse_range_f(args.sl_fast)
    tp_list = parse_range_f(args.tp)
    trail_list = parse_range_f(args.trail)
    # tstop är heltal
    tstop_list = parse_range(args.tstop)

    if args.split:
        train, test = time_split(df, args.split)
        if len(train) < 50 or len(test) < 50:
            raise SystemExit("För lite data i train/test efter split.")

        # Optimize på TRAIN
        lead_train = leaderboard(
            train, rb, rs, sl_list,
            tp_list=tp_list, trail_list=trail_list, tstop_list=tstop_list,
            fee_pct=args.fee, slippage_bps=args.slip,
            min_trades=args.min_trades, max_dd_pct=args.max_dd, min_pf=args.min_pf,
            sort_by=args.sort_by
        )
        if lead_train.empty:
            print("Inga resultat som klarar kriterierna på TRAIN.")
            return

        Path(args.out).write_text(lead_train.to_csv(index=False), encoding="utf-8")
        print("=== TRAIN – topp 10 ===")
        print(lead_train.head(10).to_string(index=False))

        if args.print_best:
            best_train = print_best_row(lead_train, "TRAIN")
        else:
            best_train = lead_train.iloc[0]

        # Testa bästa rad på TEST
        b_rb = int(best_train["rsi_buy"])
        b_rs = int(best_train["rsi_sell"])
        b_sl = float(best_train["sl_fast_pct"])
        b_tp = float(best_train.get("tp_pct", 0.0))
        b_tr = float(best_train.get("trail_pct", 0.0))
        b_ts = int(best_train.get("tstop_bars", 0))

        sig_test = build_signals(test, rsi_buy=b_rb, rsi_sell=b_rs)
        res_test = run_backtest(
            sig_test,
            fee_pct=args.fee,
            slippage_bps=args.slip,
            stop_pct=b_sl,
            tp_pct=b_tp,
            trail_pct=b_tr,
            time_stop=b_ts,
        )

        print("\n=== TEST – utvärdering av bäst från TRAIN ===")
        print(pd.Series(res_test["stats"]).to_string())

        if args.print_best:
            print("\n>>> Parametrar (bäst på TRAIN) som testades på TEST:")
            print(f"rsi_buy={b_rb}, rsi_sell={b_rs}, sl_fast_pct={b_sl}, tp_pct={b_tp}, trail_pct={b_tr}, tstop_bars={b_ts}")

    else:
        # Optimize på hela perioden
        lead = leaderboard(
            df, rb, rs, sl_list,
            tp_list=tp_list, trail_list=trail_list, tstop_list=tstop_list,
            fee_pct=args.fee, slippage_bps=args.slip,
            min_trades=args.min_trades, max_dd_pct=args.max_dd, min_pf=args.min_pf,
            sort_by=args.sort_by
        )
        if lead.empty:
            print("Inga resultat som klarar kriterierna.")
            return

        Path(args.out).write_text(lead.to_csv(index=False), encoding="utf-8")
        print("=== Leaderboard – topp 20 ===")
        print(lead.head(20).to_string(index=False))

        if args.print_best:
            print_best_row(lead, "FULL PERIOD")

        print(f"\nSparat till {args.out}")


if __name__ == "__main__":
    main()

