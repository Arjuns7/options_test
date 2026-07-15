import json
import pandas as pd

with open('real-intraday-data.js') as f:
    content = f.read()

json_str = content.split('const RealIntradayData = ')[1].split('};')[0].strip() + '}'
json_str = json_str.replace("    NIFTY:", '"NIFTY":').replace("    BANKNIFTY:", '"BANKNIFTY":')

data = json.loads(json_str)

df = pd.DataFrame(data["NIFTY"])
df = df[df["date"] == "2026-07-13"].copy()
df['EMA_9'] = df['close'].ewm(span=9, adjust=False).mean()
# Add 20 EMA to see if it acts as a filter
df['EMA_20'] = df['close'].ewm(span=20, adjust=False).mean()

print("Nifty 15-Min candles with 9 EMA and 20 EMA for July 13, 2026:")
for idx, row in df.iterrows():
    minutes = 9 * 60 + 15 + row["tickIdx"] * 15
    h = int(minutes // 60)
    m = int(minutes % 60)
    time_str = f"{h:02d}:{m:02d}"
    print(f"Time {time_str} | Open {row['open']} | High {row['high']} | Low {row['low']} | Close {row['close']} | EMA_9 {round(row['EMA_9'], 2)} | EMA_20 {round(row['EMA_20'], 2)}")
