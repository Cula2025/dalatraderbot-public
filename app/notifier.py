import os, requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT  = os.getenv("TELEGRAM_CHAT_ID", "").strip()

def send_telegram(text: str) -> bool:
    if not TOKEN or not CHAT:
        print(f"[notify ✖] Telegram ej konfigurerat. Meddelande bara i logg:\n{text}")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT, "text": text},
            timeout=10
        )
        ok = r.ok and r.json().get("ok", False)
        print(f"[notify {'✔' if ok else '✖'}] Telegram svar: {r.status_code} {r.text[:120]}")
        return ok
    except Exception as e:
        print(f"[notify ✖] Telegram-fel: {e}")
        return False
