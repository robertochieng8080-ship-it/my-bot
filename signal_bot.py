import os, requests, pandas as pd, yfinance as yf
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAIRS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "GC=F", "GBPJPY=X", "AUDUSD=X"]
NAMES = ["EURUSD", "GBPUSD", "USDJPY", "GOLD", "GBPJPY", "AUDUSD"]

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def is_news_time():
    now = datetime.utcnow()
    mins = now.hour*60 + now.minute
    # High impact news blackout UTC - 8:30am EST = 12:30 UTC, 10am EST=14:00 UTC, 2pm EST=18:00 UTC
    blackout = [
        (12*60+25, 13*60+15), # US 8:30 news (CPI,NFP,PPI)
        (14*60+0, 14*60+45), # US 10:00 news
        (18*60+0, 19*60+0), # FOMC
        (7*60+55, 8*60+30), # EU open high volatility
    ]
    for s,e in blackout:
        if s <= mins <= e:
            print(f"News blackout {now.strftime('%H:%M UTC')} - skipping")
            return True
    return False

def get_levels(df, bullish):
    recent = df.tail(30)
    ob = None
    if bullish:
        for i in range(len(recent)-5, 5, -1):
            if recent['Close'].iloc[i] < recent['Open'].iloc[i]:
                ob = recent.iloc[i]; break
    else:
        for i in range(len(recent)-5, 5, -1):
            if recent['Close'].iloc[i] > recent['Open'].iloc[i]:
                ob = recent.iloc[i]; break
    if ob is None: ob = recent.iloc[-10]
    entry = (float(ob['High'])+float(ob['Low']))/2
    atr = float((recent['High']-recent['Low']).mean())
    if bullish:
        sl = float(ob['Low']) - atr*0.2
        if entry-sl < atr*0.3: sl = entry - atr*0.8
        risk = entry-sl
        tp1 = entry + risk*3.0
        tp2 = entry + risk*5.0
    else:
        sl = float(ob['High']) + atr*0.2
        if sl-entry < atr*0.3: sl = entry + atr*0.8
        risk = sl-entry
        tp1 = entry - risk*3.0
        tp2 = entry - risk*5.0
    return entry, sl, tp1, tp2

def check_pair(pair, name):
    try:
        # 15M for entry
        df = yf.download(pair, period="5d", interval="15m", progress=False)
        if len(df) < 50: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        # 1H for HTF filter
        df1h = yf.download(pair, period="10d", interval="1h", progress=False)
        if isinstance(df1h.columns, pd.MultiIndex): df1h.columns = df1h.columns.get_level_values(0)
        ema50_1h = float(df1h['Close'].ewm(span=50).mean().iloc[-1])
        close_1h = float(df1h['Close'].iloc[-1])
        htf_bull = close_1h > ema50_1h
        htf_bear = close_1h < ema50_1h

        last_close = float(df['Close'].iloc[-1])
        high_10 = float(df['High'].rolling(10).max().iloc[-2])
        low_10 = float(df['Low'].rolling(10).min().iloc[-2])
        ema24 = float(df['Close'].ewm(span=24).mean().iloc[-1])
        ema5 = float(df['Close'].ewm(span=5).mean().iloc[-1])

        bullish_bos = last_close > high_10 and ema5 > ema24 and htf_bull
        bearish_bos = last_close < low_10 and ema5 < ema24 and htf_bear

        if is_news_time():
            return None # Skip during news

        if bullish_bos:
            entry, sl, tp1, tp2 = get_levels(df, True)
            return f"🟢 *{name} BUY - SMC 24-5*\n\n*HTF 1H:* Above EMA50 ✅ {ema50_1h:.5f}\n*BOS:* {high_10:.5f} broken\n📍 *ENTRY:* `{entry:.5f}`\n🛑 *SL:* `{sl:.5f}`\n🎯 *TP1:* `{tp1:.5f}` (RR 1:3)\n🎯 *TP2:* `{tp2:.5f}` (RR 1:5)\n\n_Time: {datetime.utcnow().strftime('%H:%M UTC')}_"

        if bearish_bos:
            entry, sl, tp1, tp2 = get_levels(df, False)
            return f"🔴 *{name} SELL - SMC 24-5*\n\n*HTF 1H:* Below EMA50 ✅ {ema50_1h:.5f}\n*BOS:* {low_10:.5f} broken\n📍 *ENTRY:* `{entry:.5f}`\n🛑 *SL:* `{sl:.5f}`\n🎯 *TP1:* `{tp1:.5f}` (RR 1:3)\n🎯 *TP2:* `{tp2:.5f}` (RR 1:5)\n\n_Time: {datetime.utcnow().strftime('%H:%M UTC')}_"

    except Exception as e:
        print(f"{name} err {e}")
        return None

print("SMC 24-5 PRO + HTF + News Filter LIVE")
for p,n in zip(PAIRS, NAMES):
    s = check_pair(p,n)
    if s: send_telegram(s)
print("Done")
