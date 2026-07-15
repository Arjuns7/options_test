import json
import pandas as pd
import numpy as np

with open('real-intraday-data.js') as f:
    content = f.read()

json_str = content.split('const RealIntradayData = ')[1].split('};')[0].strip() + '}'
json_str = json_str.replace("    NIFTY:", '"NIFTY":').replace("    BANKNIFTY:", '"BANKNIFTY":')
data = json.loads(json_str)

df = pd.DataFrame(data["NIFTY"])
# Sort by date and tickIdx
df = df.sort_values(by=['date', 'tickIdx']).reset_index(drop=True)

# Calculate indicators globally on the entire 6 months of data (same as live bot warm up)
df['EMA'] = df['close'].ewm(span=9, adjust=False).mean()

# Calculate ADX (14)
df['h_l'] = df['high'] - df['low']
df['h_pc'] = (df['high'] - df['close'].shift(1)).abs()
df['l_pc'] = (df['low'] - df['close'].shift(1)).abs()
df['tr'] = df[['h_l', 'h_pc', 'l_pc']].max(axis=1)

df['up_move'] = df['high'] - df['high'].shift(1)
df['down_move'] = df['low'].shift(1) - df['low']

df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0.0)
df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0.0)

df['tr_smoothed'] = df['tr'].ewm(alpha=1/14, adjust=False).mean()
df['plus_dm_smoothed'] = df['plus_dm'].ewm(alpha=1/14, adjust=False).mean()
df['minus_dm_smoothed'] = df['minus_dm'].ewm(alpha=1/14, adjust=False).mean()

df['plus_di'] = 100 * (df['plus_dm_smoothed'] / df['tr_smoothed'])
df['minus_di'] = 100 * (df['minus_dm_smoothed'] / df['tr_smoothed'])

df['dx'] = 100 * ((df['plus_di'] - df['minus_di']).abs() / (df['plus_di'] + df['minus_di']).abs())
df['ADX'] = df['dx'].ewm(alpha=1/14, adjust=False).mean()

# Filter for today
df_today = df[df["date"] == "2026-07-15"].copy()

print("Signal Logs for Nifty with full EMA warm-up on July 15, 2026:")
for i in range(2, len(df_today)+1):
    sub_df = df_today.iloc[:i]
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
        time_str = f"{h:02d}:{m:02d}"
        
        adx_val = sub_df['ADX'].iloc[-1]
        status = "ALLOWED" if adx_val > 25 else "BLOCKED"
        print(f"Time {time_str} | Close {close1} | EMA {round(ema1, 2)} | Signal {signal:<7} | ADX {round(adx_val, 2)} | Status: {status}")
