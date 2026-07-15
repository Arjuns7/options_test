import json
import math
import datetime
import pandas as pd
import numpy as np

# --- Black-Scholes Formula ---
def erf(x):
    a1 =  0.254829592
    a2 = -0.284496736
    a3 =  1.421413741
    a4 = -1.453152027
    a5 =  1.061405429
    p  =  0.3275911
    sign = 1
    if x < 0:
        sign = -1
    x = abs(x)
    t = 1.0/(1.0 + p*x)
    y = 1.0 - (((((a5*t + a4)*t) + a3)*t + a2)*t + a1)*t*math.exp(-x*x)
    return sign*y

def norm_cdf(x):
    return 0.5 * (1.0 + erf(x / math.sqrt(2.0)))

def black_scholes(option_type, S, K, T, r, sigma):
    if T <= 0:
        return max(0.0, S - K) if option_type == 'C' else max(0.0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option_type == 'C':
        return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    else:
        return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)

def get_expiry_date(date_str):
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    days_ahead = 3 - dt.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    expiry_dt = dt + datetime.timedelta(days=days_ahead)
    return expiry_dt

# --- Load Intraday Data ---
with open('real-intraday-data.js') as f:
    content = f.read()

json_str = content.split('const RealIntradayData = ')[1].split('};')[0].strip() + '}'
json_str = json_str.replace("    NIFTY:", '"NIFTY":').replace("    BANKNIFTY:", '"BANKNIFTY":')
data = json.loads(json_str)

df = pd.DataFrame(data["NIFTY"])
df = df[df["date"] == "2026-07-14"].copy()
df['datetime'] = pd.to_datetime(df['date'])
df = df.sort_values(by=['tickIdx']).reset_index(drop=True)

df['EMA_9'] = df['close'].ewm(span=9, adjust=False).mean()

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

# Print candle closes to understand direction
print("Nifty Closes today:")
for idx, row in df.iterrows():
    minutes = 9 * 60 + 15 + row["tickIdx"] * 15
    h = int(minutes // 60)
    m = int(minutes % 60)
    time_str = f"{h:02d}:{m:02d}"
    print(f"Time {time_str} | Close {row['close']}")

# Simulating specific trades:
# Trade 1: CE Buy at 10:45 AM
# Spot: 24,121.30, Strike: 24,050 CE
def sim_trade(entry_tick_idx, op_type, strike, sl_pct=0.15, tp_pct=0.60):
    entry_tick = df[df['tickIdx'] == entry_tick_idx].iloc[0]
    date_str = entry_tick['date']
    spot = entry_tick['close']
    
    expiry_dt = get_expiry_date(date_str)
    days_diff = (expiry_dt - datetime.datetime.strptime(date_str, "%Y-%m-%d")).days
    hours_left = 15.5 - (9.25 + entry_tick_idx * 0.25)
    T_entry = max(0.0001, (days_diff + hours_left / 24) / 365.25)
    
    entry_premium = black_scholes(op_type, spot, strike, T_entry, entry_tick['r'], entry_tick['iv'] / 100)
    
    print(f"\nSimulating {op_type} Trade from tickIdx {entry_tick_idx}:")
    print(f"  * Entry Spot: {spot} | Entry Premium: {round(entry_premium, 2)}")
    sl_limit = entry_premium * (1 - sl_pct)
    tp_limit = entry_premium * (1 + tp_pct)
    print(f"  * SL Limit (15%): {round(sl_limit, 2)} | TP Limit (60%): {round(tp_limit, 2)}")
    
    for idx in range(entry_tick_idx + 1, 25):
        tick = df[df['tickIdx'] == idx].iloc[0]
        spot_now = tick['close']
        
        hours_left = 15.5 - (9.25 + idx * 0.25)
        T_now = max(0.0001, (days_diff + hours_left / 24) / 365.25)
        
        current_premium = black_scholes(op_type, spot_now, strike, T_now, tick['r'], tick['iv'] / 100)
        
        minutes = 9 * 60 + 15 + idx * 15
        h = int(minutes // 60)
        m = int(minutes % 60)
        time_str = f"{h:02d}:{m:02d}"
        
        print(f"  Time {time_str} | Spot {spot_now} | Premium {round(current_premium, 2)}")
        
        if current_premium <= sl_limit:
            pnl = (sl_limit - entry_premium) * 150
            print(f"  [STOP LOSS HIT] at {time_str}! Premium: {round(current_premium, 2)} | P&L: -INR {abs(round(pnl, 2))}")
            return
        elif current_premium >= tp_limit:
            pnl = (tp_limit - entry_premium) * 150
            print(f"  [TARGET HIT] at {time_str}! Premium: {round(current_premium, 2)} | P&L: +INR {round(pnl, 2)}")
            return
            
    # Time Exit
    tick_24 = df[df['tickIdx'] == 24].iloc[0]
    spot_now = tick_24['close']
    T_now = max(0.0001, (days_diff + 0.25 / 24) / 365.25)
    current_premium = black_scholes(op_type, spot_now, strike, T_now, tick_24['r'], tick_24['iv'] / 100)
    pnl = (current_premium - entry_premium) * 150
    print(f"  [TIME EXIT] at 15:15! Premium: {round(current_premium, 2)} | P&L: {round(pnl, 2)}")

# 10:45 AM is tickIdx 6
sim_trade(6, 'C', 24050)
# 11:30 AM is tickIdx 9
sim_trade(9, 'P', 24150)
# 1:45 PM is tickIdx 17
sim_trade(17, 'P', 24100)
