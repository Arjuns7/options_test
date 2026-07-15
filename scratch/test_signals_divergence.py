import json
import pandas as pd

with open('real-intraday-data.js') as f:
    content = f.read()

json_str = content.split('const RealIntradayData = ')[1].split('};')[0].strip() + '}'
json_str = json_str.replace("    NIFTY:", '"NIFTY":').replace("    BANKNIFTY:", '"BANKNIFTY":')

data = json.loads(json_str)

df = pd.DataFrame(data["NIFTY"])
df = df[df["date"] == "2026-07-13"].copy()
df['EMA'] = df['close'].ewm(span=9, adjust=False).mean()

print("Simulating check_crossover on today's Nifty data:")
print("1. Using iloc[-2] and iloc[-3] (Current code):")
for i in range(3, len(df)+1):
    sub_df = df.iloc[:i]
    prev_close1 = sub_df['close'].iloc[-2]
    prev_ema1 = sub_df['EMA'].iloc[-2]
    prev_close2 = sub_df['close'].iloc[-3]
    prev_ema2 = sub_df['EMA'].iloc[-3]
    
    signal = 'NONE'
    if prev_close1 > prev_ema1 and prev_close2 <= prev_ema2:
        signal = 'BULLISH'
    elif prev_close1 < prev_ema1 and prev_close2 >= prev_ema2:
        signal = 'BEARISH'
        
    if signal != 'NONE':
        time_idx = sub_df['tickIdx'].iloc[-1]
        minutes = 9 * 60 + 15 + time_idx * 15
        h = minutes // 60
        m = minutes % 60
        print(f"Time {h:02d}:{m:02d} | Triggered: {signal} | Checked candle: {sub_df['date'].iloc[-2]} Index {sub_df['tickIdx'].iloc[-2]}")

print("\n2. Using iloc[-1] and iloc[-2] (Corrected code):")
for i in range(2, len(df)+1):
    sub_df = df.iloc[:i]
    close1 = sub_df['close'].iloc[-1]
    ema1 = sub_df['EMA'].iloc[-1]
    close2 = sub_df['close'].iloc[-2]
    ema2 = sub_df['EMA'].iloc[-2]
    
    signal = 'NONE'
    if close1 > ema1 and close2 <= ema2:
        signal = 'BULLISH'
    elif close1 < ema1 and close2 >= ema2:
        signal = 'BEARISH'
        
    if signal != 'NONE':
        time_idx = sub_df['tickIdx'].iloc[-1]
        minutes = 9 * 60 + 15 + time_idx * 15
        h = minutes // 60
        m = minutes % 60
        print(f"Time {h:02d}:{m:02d} | Triggered: {signal} | Checked candle: {sub_df['date'].iloc[-1]} Index {sub_df['tickIdx'].iloc[-1]}")
