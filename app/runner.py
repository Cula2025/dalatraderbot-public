import os, subprocess, time, datetime, hashlib, json, pathlib, sys
from notifier import send_telegram

interval = int(os.getenv("SCAN_INTERVAL_SECS", "300"))
tz = os.getenv("TZ", "Europe/Stockholm")

STATE_DIR = pathlib.Path("/app/state")
STATE_DIR.mkdir(parents=True, exist_ok=True)
SEEN_FILE = STATE_DIR / "seen.json"

def load_seen():
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()

def save_seen(seen: set):
    try:
        SEEN_FILE.write_text(json.dumps(sorted(list(seen))), encoding="utf-8")
    except Exception as e:
        print(f"[runner] kunde inte spara seen: {e}", flush=True)

def is_signal_line(line: str) -> bool:
    s = line.strip().upper()
    return ("KÖP" in s) or ("SÄLJ" in s) or ("KOP" in s) or ("SALJ" in s)

def line_hash(s: str) -> str:
    return hashlib.sha1(s.strip().encode("utf-8")).hexdigest()

print(f"Starting alert loop with interval {interval}s. TZ={tz}", flush=True)
seen = load_seen()

while True:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] Running alert pass...", flush=True)
    try:
        proc = subprocess.run(
            ["python", "/app/alert_batch.py", "--csv", "/app/tickers_se.csv",
             "--period", "6mo", "--interval", "1d", "--only-signals"],
            capture_output=True, text=True, check=False
        )

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        if stdout:
            print(stdout, end="")

        new_lines = []
        for line in stdout.splitlines():
            if not is_signal_line(line):
                continue
            h = line_hash(line)
            if h not in seen:
                seen.add(h)
                new_lines.append(line)

        if new_lines:
            msg = "📣 Nya signaler:\n" + "\n".join(new_lines)
            send_telegram(msg)

        if stderr.strip():
            print(f"[stderr]\n{stderr}", file=sys.stderr)

        save_seen(seen)

    except Exception as e:
        print(f"[runner] error: {e}", flush=True)

    print(f"Sleeping {interval}s...", flush=True)
    time.sleep(interval)
