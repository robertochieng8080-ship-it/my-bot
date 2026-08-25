import os, requests
print("Starting test...")

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

print(f"Token exists: {bool(TOKEN)}")
print(f"Chat ID: {CHAT_ID}")

if not TOKEN or not CHAT_ID:
    print("ERROR: Secrets missing!")
else:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": "✅ TEST SUCCESS! GitHub is connected to Telegram! Your SMC bot will now work."}
    r = requests.post(url, data=data)
    print(f"Telegram response: {r.text}")

print("Done")
