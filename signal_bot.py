import yfinance as yf
import pandas as pd
import requests, os, json
from datetime import datetime, timedelta

PAIRS = {"EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "GOLD": "GC=F", "AUDUSD": "AUDUSD=X"}
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SENT_FILE = "last_signals.json"

def send(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def load_sent():
    if os.path.exists(SENT_FILE):
        try: return json.load(open(SENT_FILE))
        except: return {}
    return {}

def can_send(pair, sent):
    # Don't spam same pair within 2 hours
    if pair in sent:
        last = datetime.fromisoformat(sent[pair])
        if datetime.utcnow() - last < timedelta(hours=2):
            return False
    return True

def check_fvg(df):
    # Bullish FVG: Low[2] > High[0]
    for i in range(len(df)-5, len(df)-2):
        if df['Low'].iloc[i+2] > df['High'].iloc[i]:
            return {"type": "BULL_FVG", "zone_low": df['High'].iloc[i], "zone_high": df['Low'].iloc[i+2]}
        if df['High'].iloc[i+2] < df['Low'].iloc[i]:
            return {"type": "BEAR_FVG", "zone_low": df['High'].iloc[i+2], "zone_high": df['Low'].iloc[i]}
    return None

def check_demand_supply(df):
    atr = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
    for i in range(len(df)-10, len(df)-3):
        base = df.iloc[i-2:i+1]
        imp = df.iloc[i+1]
        base_range = base['High'].max() - base['Low'].min()
        # Small base + big impulse = fresh zone
        if base_range < atr * 0.8 and (imp['Close'] - imp['Open']) > atr:
            if imp['Close'] > base['High'].max(): # Demand
                return {"type": "DEMAND", "zone_low": base['Low'].min(), "zone_high": base['High'].max()}
            if imp['Close'] < base['Low'].min(): # Supply
                return {"type": "SUPPLY", "zone_low": base['Low'].min(), "zone_high": base['High'].max()}
    return None

def check_liquidity_sweep(df):
    recent_high = df['High'].tail(20).max()
    recent_low = df['Low'].tail(20).min()
    last = df.iloc[-2]
    # Bullish sweep: wick below low then close above
    if last['Low'] < recent_low and last['Close'] > recent_low:
        return "BULL_SWEEP"
    if last['High'] > recent_high and last['Close'] < recent_high:
        return "BEAR_SWEEP"
    return None

def analyze_pair(name, ticker, sent):
    df15 = yf.download(ticker, period="5d", interval="15m", progress=False, auto_adjust=True)
    df1h = yf.download(ticker, period="10d", interval="1h", progress=False, auto_adjust=True)
    if len(df15) < 60 or len(df1h) < 60: return

    df15['EMA24'] = df15['Close'].ewm(span=24).mean()
    df15['EMA5'] = df15['Close'].ewm(span=5).mean()
    df1h['EMA50'] = df1h['Close'].ewm(span=50).mean()

    last = df15.iloc[-2]
    curr = df15.iloc[-1]
    htf_bull = df1h['Close'].iloc[-1] > df1h['EMA50'].iloc[-1]
    htf_bear = not htf_bull

    recent_high = df15['High'].tail(20).max()
    recent_low = df15['Low'].tail(20).min()

    bos_bull = last['Close'] > recent_high
    bos_bear = last['Close'] < recent_low

    score = 0
    reasons = []
    entry_zone = None

    # 1. HTF FILTER (Mandatory)
    if not (htf_bull or htf_bear): return

    # 2. SMC BOS + OB
    if bos_bull and last['EMA5'] > last['EMA24']:
        score += 1; reasons.append("SMC BOS")
        entry_zone = last['Low']
    if bos_bear and last['EMA5'] < last['EMA24']:
        score += 1; reasons.append("SMC BOS")
        entry_zone = last['High']

    # 3. Demand/Supply
    ds = check_demand_supply(df15)
    if ds:
        if ds['type'] == "DEMAND" and htf_bull:
            score += 1; reasons.append("DEMAND")
            entry_zone = (ds['zone_low'] + ds['zone_high'])/2
        if ds['type'] == "SUPPLY" and htf_bear:
            score += 1; reasons.append("SUPPLY")
            entry_zone = (ds['zone_low'] + ds['zone_high'])/2

    # 4. Pullback to EMA24
    dist_to_ema = abs(last['Close'] - last['EMA24']) / last['Close'] * 100
    if dist_to_ema < 0.15:
        score += 1; reasons.append("PULLBACK 50%")

    # 5. ICT FVG
    fvg = check_fvg(df15)
    if fvg:
        if fvg['type'] == "BULL_FVG" and htf_bull:
            score += 1; reasons.append("ICT FVG")
            entry_zone = (fvg['zone_low'] + fvg['zone_high'])/2
        if fvg['type'] == "BEAR_FVG" and htf_bear:
            score += 1; reasons.append("ICT FVG")
            entry_zone = (fvg['zone_low'] + fvg['zone_high'])/2

    # 6. Liquidity Sweep
    sweep = check_liquidity_sweep(df15)
    if (sweep == "BULL_SWEEP" and htf_bull) or (sweep == "BEAR_SWEEP" and htf_bear):
        score += 1; reasons.append("LIQUIDITY SWEEP")

    # SEND ONLY IF CONFLUENCE >=3
    if score >= 3 and can_send(name, sent) and entry_zone:
        is_buy = htf_bull and ("DEMAND" in str(reasons) or bos_bull or (fvg and fvg['type']=="BULL_FVG"))
        direction = "BUY" if is_buy else "SELL"
        emoji = "🟢" if is_buy else "🔴"

        # SL/TP calc
        atr = (df15['High'] - df15['Low']).rolling(14).mean().iloc[-1]
        if is_buy:
            sl = entry_zone - atr * 0.5
            tp1 = entry_zone + (entry_zone - sl) * 3
            tp2 = entry_zone + (entry_zone - sl) * 5
        else:
            sl = entry_zone + atr * 0.5
            tp1 = entry_zone - (sl - entry_zone) * 3
            tp2 = entry_zone - (sl - entry_zone) * 5

        grade = "A+" if score >=4 else "A" if score==3 else "B"

        msg = f"{emoji} {name} {direction} - CONFLUENCE {score}/5 ({grade})\n"
        msg += f"Types: {' + '.join(reasons)}\n"
        msg += f"HTF 1H: {'Above' if htf_bull else 'Below'} EMA50 ✅\n"
        msg += f"📍 ENTRY: {entry_zone:.5f}\n🛑 SL: {sl:.5f}\n"
        msg += f"🎯 TP1: {tp1:.5f} (1:3)\n🎯 TP2: {tp2:.5f} (1:5)\n"
        msg += f"Accuracy: {'HIGH' if score>=4 else 'MEDIUM'} - {score} strategies at same level\nTime: {datetime.utcnow().strftime('%H:%M UTC')}"

        send(msg)
        sent[name] = datetime.utcnow().isoformat()
        json.dump(sent, open(SENT_FILE, 'w'))

# Run
sent = load_sent()
for n, t in PAIRS.items():
    try: analyze_pair(n, t, sent)
    except Exception as e: print(f"{n} err {e}")

print("PRO MAX scan done")
