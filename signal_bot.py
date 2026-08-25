import os, requests, pandas as pd, numpy as np, yfinance as yf
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAIRS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "XAUUSD=X", "GBPJPY=X", "AUDUSD=X"]
NAMES = ["EURUSD", "GBPUSD", "USDJPY", "GOLD", "GBPJPY", "AUDUSD"]

def send_telegram(msg):
    if not TOKEN or not CHAT_ID:
        print("Missing secrets")
        return
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        print(f"Telegram: {r.text}")
    except Exception as e:
        print(f"Telegram error: {e}")

def check_smc(pair, name):
    try:
        df = yf.download(pair, period="2d", interval="15m", progress=False)
        if len(df) < 50:
            return None
        # Flatten if multiindex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # SMC 24-5 Logic: BOS + OB
        # Simple: detect Break of Structure + Order Block
        high = df['High'].rolling(10).max()
        low = df['Low'].rolling(10).min()
        
        last_close = float(df['Close'].iloc[-1])
        prev_high = float(high.iloc[-2])
        prev_low = float(low.iloc[-2])
        
        # Bullish BOS: close breaks previous 10-candle high + bullish momentum
        bullish_bos = last_close > prev_high and df['Close'].iloc[-1] > df['Open'].iloc[-1]
        bearish_bos = last_close < prev_low and df['Close'].iloc[-1] < df['Open'].iloc[-1]
        
        # Volume / momentum filter (24-5)
        ema_24 = df['Close'].ewm(span=24).mean().iloc[-1]
        ema_5 = df['Close'].ewm(span=5).mean().iloc[-1]
        
        if bullish_bos and ema_5 > ema_24:
            return f"🟢 *{name} BULLISH BOS*\nPrice: {last_close:.5f}\nBreak above {prev_high:.5f}\nEMA 5>24 ✅\nTime: {datetime.utcnow().strftime('%H:%M UTC')}\nSetup: SMC 24-5 Buy"
        if bearish_bos and ema_5 < ema_24:
            return f"🔴 *{name} BEARISH BOS*\nPrice: {last_close:.5f}\nBreak below {prev_low:.5f}\nEMA 5<24 ✅\nTime: {datetime.utcnow().strftime('%H:%M UTC')}\nSetup: SMC 24-5 Sell"
        return None
    except Exception as e:
        print(f"{name} error: {e}")
        return None

print(f"Starting SMC Bot 24-5 - 6 Pairs - {datetime.utcnow()}")
signals = []
for p, n in zip(PAIRS, NAMES):
    sig = check_smc(p, n)
    if sig:
        signals.append(sig)

if signals:
    for s in signals:
        send_telegram(s)
else:
    print("No SMC setup now - bot is LIVE and checking every 15min")
    # Uncomment next line if you want a heartbeat message when no setup:
    # send_telegram("✅ Bot check: No setup yet - LIVE")

print("Done")
