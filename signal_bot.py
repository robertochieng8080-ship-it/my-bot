import os, requests, pandas as pd, json
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SYMBOLS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CHF", "EUR/GBP"]

CONFIG = {"SWING_LOOKBACK":5,"RSI_PERIOD":14,"RSI_BUY_THRESHOLD":50,"RSI_SELL_THRESHOLD":50,"RISK_REWARD_RATIO":3.0,"SL_BUFFER_PIPS":3,"MAX_BOS_AGE":30,"STATE_FILE":"bot_state.json","CSV_FILE":"signal_log.csv"}

def send_telegram(msg):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except: pass

def load_state():
    try:
        with open(CONFIG["STATE_FILE"]) as f: return json.load(f)
    except: return {"last_alerted_candle": {}}

def save_state(s):
    with open(CONFIG["STATE_FILE"], "w") as f: json.dump(s, f, indent=2)

def get_candles(symbol):
    yf = symbol.replace("/","")+"=X"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf}"
    r = requests.get(url, params={"interval":"5m","range":"2d"}, headers={"User-Agent":"Mozilla/5.0"}, timeout=15)
    data=r.json();res=data.get("chart",{}).get("result",[{}])[0]
    ts=res.get("timestamp",[]);q=res.get("indicators",{}).get("quote",[{}])[0]
    rows=[]
    for i in range(len(ts)):
        if q.get("close",[])[i] is None: continue
        rows.append({"time":pd.to_datetime(ts[i],unit='s'),"open":q["open"][i],"high":q["high"][i],"low":q["low"][i],"close":q["close"][i]})
    return pd.DataFrame(rows).sort_values("time").reset_index(drop=True)

def rsi(c,p):
    d=c.diff();g=d.clip(lower=0);l=-d.clip(upper=0)
    ag=g.ewm(alpha=1/p,min_periods=p,adjust=False).mean();al=l.ewm(alpha=1/p,min_periods=p,adjust=False).mean()
    rs=ag/al.replace(0,float('nan'));r=100-(100/(1+rs))
    return r.where(al!=0,100).fillna(50)

def swings(df,lb):
    h,l=[],[]
    for i in range(lb,len(df)-lb):
        ch=df["high"].iloc[i];cl=df["low"].iloc[i]
        if ch>df["high"].iloc[i-lb:i].max() and ch>df["high"].iloc[i+1:i+lb+1].max(): h.append((i,ch))
        if cl<df["low"].iloc[i-lb:i].min() and cl<df["low"].iloc[i+1:i+lb+1].min(): l.append((i,cl))
    return h,l

def bos(df,lb):
    hi,lo=swings(df,lb)
    if not hi or not lo: return None
    for idx,price in reversed(hi):
        if idx>=len(df)-3: continue
        after=df.iloc[idx+1:];br=after[after["close"]>price]
        if not br.empty and len(df)-br.index[0]<=CONFIG["MAX_BOS_AGE"]: return {"type":"bullish","bos_idx":br.index[0]}
    for idx,price in reversed(lo):
        if idx>=len(df)-3: continue
        after=df.iloc[idx+1:];br=after[after["close"]<price]
        if not br.empty and len(df)-br.index[0]<=CONFIG["MAX_BOS_AGE"]: return {"type":"bearish","bos_idx":br.index[0]}
    return None

def ob(df,b):
    r=df.iloc[max(0,b["bos_idx"]-15):b["bos_idx"]]
    if b["type"]=="bullish":
        be=r[r["close"]<r["open"]]
        if be.empty: return None,None
        x=be.iloc[-1];return x["high"],x["low"]
    else:
        bu=r[r["close"]>r["open"]]
        if bu.empty: return None,None
        x=bu.iloc[-1];return x["high"],x["low"]

state=load_state()
for sym in SYMBOLS:
    try:
        df=get_candles(sym)
        if len(df)<40: continue
        df["rsi"]=rsi(df["close"],CONFIG["RSI_PERIOD"])
        curr=df.iloc[-1];iso=curr["time"].isoformat()
        if state["last_alerted_candle"].get(sym)==iso: continue
        b=bos(df,CONFIG["SWING_LOOKBACK"])
        if not b: continue
        ob_h,ob_l=ob(df,b)
        if ob_h is None: continue
        if not (curr["low"]<=ob_h and curr["high"]>=ob_l): continue
        direction=None
        if b["type"]=="bullish" and curr["rsi"]>50: direction="BUY"
        if b["type"]=="bearish" and curr["rsi"]<50: direction="SELL"
        if not direction: continue
        pip=0.01 if "JPY" in sym else 0.0001
        sl=(ob_l-3*pip) if direction=="BUY" else (ob_h+3*pip)
        dist=abs(curr["close"]-sl)
        tp=curr["close"]+dist*3.0 if direction=="BUY" else curr["close"]-dist*3.0
        dec=3 if "JPY" in sym else 5
        msg=f"🔔 {sym} {direction}\nEntry: {curr['close']:.{dec}f}\nSL: {sl:.{dec}f}\nTP: {tp:.{dec}f}\nRSI: {curr['rsi']:.1f}"
        send_telegram(msg)
        state["last_alerted_candle"][sym]=iso
    except: continue
save_state(state)
print("Done")
