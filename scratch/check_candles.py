import json

with open('real-intraday-data.js') as f:
    content = f.read()

json_str = content.split('const RealIntradayData = ')[1].split('};')[0].strip() + '}'
json_str = json_str.replace("    NIFTY:", '"NIFTY":').replace("    BANKNIFTY:", '"BANKNIFTY":')

try:
    data = json.loads(json_str)
    print("Nifty 15-min candles for July 10, 2026:")
    for t in data["NIFTY"]:
        if t["date"] == "2026-07-10":
            minutes = 9 * 60 + 15 + t["tickIdx"] * 15
            h = minutes // 60
            m = minutes % 60
            time_str = f"{h:02d}:{m:02d}"
            print(f"Index {t['tickIdx']} ({time_str}): Open {t['open']} | Close {t['close']}")
except Exception as e:
    print("Error parsing:", e)
