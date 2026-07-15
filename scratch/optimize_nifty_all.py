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

df_nifty = pd.DataFrame(data["NIFTY"])
# Filter for 6 months
df_nifty = df_nifty[df_nifty["date"] >= "2026-01-14"].copy()
df_nifty['datetime'] = pd.to_datetime(df_nifty['date'])
df_nifty = df_nifty.sort_values(by=['date', 'tickIdx']).reset_index(drop=True)

# Calculate indicators globally
df_nifty['h_l'] = df_nifty['high'] - df_nifty['low']
df_nifty['h_pc'] = (df_nifty['high'] - df_nifty['close'].shift(1)).abs()
df_nifty['l_pc'] = (df_nifty['low'] - df_nifty['close'].shift(1)).abs()
df_nifty['tr'] = df_nifty[['h_l', 'h_pc', 'l_pc']].max(axis=1)

df_nifty['up_move'] = df_nifty['high'] - df_nifty['high'].shift(1)
df_nifty['down_move'] = df_nifty['low'].shift(1) - df_nifty['low']

df_nifty['plus_dm'] = np.where((df_nifty['up_move'] > df_nifty['down_move']) & (df_nifty['up_move'] > 0), df_nifty['up_move'], 0.0)
df_nifty['minus_dm'] = np.where((df_nifty['down_move'] > df_nifty['up_move']) & (df_nifty['down_move'] > 0), df_nifty['down_move'], 0.0)

df_nifty['tr_smoothed'] = df_nifty['tr'].ewm(alpha=1/14, adjust=False).mean()
df_nifty['plus_dm_smoothed'] = df_nifty['plus_dm'].ewm(alpha=1/14, adjust=False).mean()
df_nifty['minus_dm_smoothed'] = df_nifty['minus_dm'].ewm(alpha=1/14, adjust=False).mean()

df_nifty['plus_di'] = 100 * (df_nifty['plus_dm_smoothed'] / df_nifty['tr_smoothed'])
df_nifty['minus_di'] = 100 * (df_nifty['minus_dm_smoothed'] / df_nifty['tr_smoothed'])

df_nifty['dx'] = 100 * ((df_nifty['plus_di'] - df_nifty['minus_di']).abs() / (df_nifty['plus_di'] + df_nifty['minus_di']).abs())
df_nifty['ADX'] = df_nifty['dx'].ewm(alpha=1/14, adjust=False).mean()

# EMAs
ema_periods = [9, 15, 21]
for p in ema_periods:
    df_nifty[f'EMA_{p}'] = df_nifty['close'].ewm(span=p, adjust=False).mean()

def run_backtest_nifty(ema_p, sl_pct, tp_pct, adx_threshold=0):
    active_trade = None
    trades = []
    
    ema_col = f'EMA_{ema_p}'
    
    for i in range(2, len(df_nifty)):
        tick = df_nifty.iloc[i]
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
            prev_tick1 = df_nifty.iloc[i-1]
            prev_tick2 = df_nifty.iloc[i-2]
            
            if prev_tick1['date'] != date_str or prev_tick2['date'] != date_str:
                continue
                
            close1 = prev_tick1['close']
            ema1 = prev_tick1[ema_col]
            close2 = prev_tick2['close']
            ema2 = prev_tick2[ema_col]
            
            signal = 'NONE'
            if close1 > ema1 and close2 <= ema2:
                signal = 'BULLISH'
            elif close1 < ema1 and close2 >= ema2:
                signal = 'BEARISH'
                
            if signal != 'NONE' and tick_idx < 24:
                # ADX Filter
                if adx_threshold > 0:
                    adx = prev_tick1['ADX']
                    if math.isnan(adx) or adx <= adx_threshold:
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

# Param grid search
ema_list = [9, 15, 21]
adx_list = [0, 20, 25]
sl_list = [0.15, 0.20, 0.25, 0.30]
tp_list = [0.30, 0.40, 0.50, 0.60]

print("Running Nifty multi-dimensional optimization...")
nifty_opt_results = []
for ema in ema_list:
    for adx in adx_list:
        for sl in sl_list:
            for tp in tp_list:
                trades = run_backtest_nifty(ema, sl, tp, adx)
                wins = [t for t in trades if t['pnl'] > 0]
                losses = [t for t in trades if t['pnl'] <= 0]
                net_pnl = sum([t['pnl'] for t in trades])
                win_rate = len(wins) / len(trades) * 100 if trades else 0.0
                nifty_opt_results.append({
                    "ema": ema,
                    "adx": adx,
                    "sl": int(sl * 100),
                    "tp": int(tp * 100),
                    "trades": len(trades),
                    "win_rate": round(win_rate, 2),
                    "pnl": round(net_pnl, 2)
                })

nifty_opt_results = sorted(nifty_opt_results, key=lambda x: x['pnl'], reverse=True)

print("\n=========================================================================")
print("          NIFTY STRATEGY OPTIMIZATION REPORT (6-MONTH)                   ")
print("=========================================================================")
print("Dataset Range: January 14, 2026 to July 13, 2026")
print("Trade Size: 150 units (2 Lots)\n")

print(f"{'Rank':<5} | {'EMA':<4} | {'ADX Filter':<10} | {'SL (%)':<7} | {'Target (%)':<10} | {'Trades':<8} | {'Win Rate':<8} | {'Net P&L (INR)':<15}")
print(f"{'-'*5} | {'-'*4} | {'-'*10} | {'-'*7} | {'-'*10} | {'-'*8} | {'-'*8} | {'-'*15}")

for rank, r in enumerate(nifty_opt_results[:15], 1):
    pnl_str = f"{'+' if r['pnl'] >= 0 else ''}INR {r['pnl']:,.2f}"
    adx_str = f"ADX > {r['adx']}" if r['adx'] > 0 else "None"
    print(f"{rank:<5} | {r['ema']:<4} | {adx_str:<10} | {r['sl']:<7} | {r['tp']:<10} | {r['trades']:<8} | {r['win_rate']:<7}% | {pnl_str:<15}")

print("=========================================================================\n")
