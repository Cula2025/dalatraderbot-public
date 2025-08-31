import os, requests
token = os.getenv("TELEGRAM_BOT_TOKEN")
chat  = os.getenv("TELEGRAM_CHAT_ID")
r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                  json={"chat_id": chat, "text": "✅ Telegram-test från Docker"},
                  timeout=10)
print(r.status_code, r.text)
