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
# Filter for 6 months
df = df[df["date"] >= "2026-01-14"].copy()
df['datetime'] = pd.to_datetime(df['date'])
df = df.sort_values(by=['date', 'tickIdx']).reset_index(drop=True)

# --- Calculate Indicators ---
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

# Run Custom Backtest
def run_backtest_custom(sl_pct, tp_pct, use_adx_filter=False):
    active_trade = None
    trades = []
    
    for i in range(2, len(df)):
        tick = df.iloc[i]
        date_str = tick['date']
        tick_idx = tick['tickIdx']
        spot = tick['close']
        
        # 1. Manage Active Trade
        if active_trade:
            expiry_dt = get_expiry_date(date_str)
            days_diff = (expiry_dt - datetime.datetime.strptime(date_str, "%Y-%m-%d")).days
            hours_left = 15.5 - (9.25 + tick_idx * 0.25)
            T_tick = max(0.0001, (days_diff + hours_left / 24) / 365.25)
            
            current_premium = black_scholes(
                active_trade['type'], 
                spot, 
                active_trade['strike'], 
                T_tick, 
                tick['r'], 
                tick['iv'] / 100
            )
            
            sl_limit = active_trade['entry_premium'] * (1 - sl_pct)
            tp_limit = active_trade['entry_premium'] * (1 + tp_pct)
            
            close_trade = False
            status = 'TIME_EXIT'
            exit_premium = current_premium
            
            if current_premium <= sl_limit:
                close_trade = True
                status = 'SL_HIT'
                exit_premium = sl_limit
            elif current_premium >= tp_limit:
                close_trade = True
                status = 'TP_HIT'
                exit_premium = tp_limit
            elif tick_idx == 24:
                close_trade = True
                status = 'TIME_EXIT'
                
            if close_trade:
                pnl = (exit_premium - active_trade['entry_premium']) * active_trade['qty']
                trades.append({
                    "pnl": round(pnl, 2)
                })
                active_trade = None
                
        # 2. Check for Crossover Signals
        else:
            prev_tick1 = df.iloc[i-1]
            prev_tick2 = df.iloc[i-2]
            
            if prev_tick1['date'] != date_str or prev_tick2['date'] != date_str:
                continue
                
            close1 = prev_tick1['close']
            ema1 = prev_tick1['EMA_9']
            close2 = prev_tick2['close']
            ema2 = prev_tick2['EMA_9']
            
            signal = 'NONE'
            if close1 > ema1 and close2 <= ema2:
                signal = 'BULLISH'
            elif close1 < ema1 and close2 >= ema2:
                signal = 'BEARISH'
                
            if signal != 'NONE' and tick_idx < 24:
                if use_adx_filter:
                    adx = prev_tick1['ADX']
                    if math.isnan(adx) or adx <= 25:
                        continue
                        
                option_type = 'C' if signal == 'BULLISH' else 'P'
                atm_strike = round(spot / 50) * 50
                strike = atm_strike - 50 if option_type == 'C' else atm_strike + 50
                
                expiry_dt = get_expiry_date(date_str)
                days_diff = (expiry_dt - datetime.datetime.strptime(date_str, "%Y-%m-%d")).days
                hours_left = 15.5 - (9.25 + tick_idx * 0.25)
                T_entry = max(0.0001, (days_diff + hours_left / 24) / 365.25)
                
                entry_premium = black_scholes(
                    option_type, 
                    spot, 
                    strike, 
                    T_entry, 
                    tick['r'], 
                    tick['iv'] / 100
                )
                
                active_trade = {
                    "entry_date": date_str,
                    "type": option_type,
                    "strike": strike,
                    "entry_spot": spot,
                    "entry_premium": entry_premium,
                    "qty": 150
                }
                
    return trades

# Configurations to test:
# 1. 15% SL / 40% TP + ADX
# 2. 15% SL / 40% TP NO ADX
# 3. 20% SL / 25% TP + ADX
# 4. 20% SL / 25% TP NO ADX

configs = [
    {"sl": 0.15, "tp": 0.40, "adx": True, "name": "Optimal (15% SL, 40% Target) + ADX > 25"},
    {"sl": 0.15, "tp": 0.40, "adx": False, "name": "Optimal (15% SL, 40% Target) - NO ADX"},
    {"sl": 0.20, "tp": 0.25, "adx": True, "name": "Current Setup (20% SL, 25% Target) + ADX > 25"},
    {"sl": 0.20, "tp": 0.25, "adx": False, "name": "Current Setup (20% SL, 25% Target) - NO ADX"}
]

print("Running comparative matrix backtests...")
matrix_results = []
for c in configs:
    trades = run_backtest_custom(c["sl"], c["tp"], c["adx"])
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    net_pnl = sum([t['pnl'] for t in trades])
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0
    matrix_results.append({
        "name": c["name"],
        "count": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 2),
        "pnl": round(net_pnl, 2)
    })

print("\n=======================================================")
print("     6-MONTH STRATEGY MATRIX COMPARISON (NIFTY)        ")
print("=======================================================")
print("Dataset Range: January 14, 2026 to July 13, 2026")
print("Position Size: 150 units (2 Lots)\n")

for r in matrix_results:
    pnl_str = f"{'+' if r['pnl'] >= 0 else ''}INR {r['pnl']:,.2f}"
    print(f"Configuration: {r['name']}")
    print(f"  * Total Trades: {r['count']}")
    print(f"  * Wins: {r['wins']} | Losses: {r['losses']}")
    print(f"  * Win Rate: {r['win_rate']}%")
    print(f"  * Net P&L: {pnl_str}")
    print("-------------------------------------------------------")
