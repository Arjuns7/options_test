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
# Filter from January 14, 2026
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

def run_backtest_monthly(use_adx_filter=False):
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
            
            sl_limit = active_trade['entry_premium'] * 0.80
            tp_limit = active_trade['entry_premium'] * 1.25
            
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
                    "date": active_trade['entry_date'],
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

trades_no = run_backtest_monthly(use_adx_filter=False)
trades_yes = run_backtest_monthly(use_adx_filter=True)

# Group by month
def get_monthly_breakdown(trades_list):
    monthly_data = {}
    for t in trades_list:
        dt = datetime.datetime.strptime(t['date'], "%Y-%m-%d")
        month_key = dt.strftime("%Y-%m (%B)")
        if month_key not in monthly_data:
            monthly_data[month_key] = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0}
            
        monthly_data[month_key]["trades"] += 1
        if t['pnl'] > 0:
            monthly_data[month_key]["wins"] += 1
        else:
            monthly_data[month_key]["losses"] += 1
        monthly_data[month_key]["pnl"] += t['pnl']
    return monthly_data

mb_no = get_monthly_breakdown(trades_no)
mb_yes = get_monthly_breakdown(trades_yes)

# Print Report
print("\n=======================================================")
print("      MONTHLY P&L BREAKDOWN (JAN - JUL 2026)           ")
print("      Nifty 15-Min EMA Crossover Strategy (2 Lots)     ")
print("=======================================================")

all_months = sorted(list(set(list(mb_no.keys()) + list(mb_yes.keys()))))

print(f"{'Month':<18} | {'BASELINE (No Filter)':<26} | {'WITH ADX > 25 FILTER':<26}")
print(f"{'-'*18} | {'-'*26} | {'-'*26}")

for m in all_months:
    no_info = mb_no.get(m, {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0})
    yes_info = mb_yes.get(m, {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0})
    
    no_pnl_str = f"{'+' if no_info['pnl'] >= 0 else ''}INR {no_info['pnl']:,.2f}"
    yes_pnl_str = f"{'+' if yes_info['pnl'] >= 0 else ''}INR {yes_info['pnl']:,.2f}"
    
    no_details = f"{no_pnl_str:<14} ({no_info['wins']}W/{no_info['losses']}L)"
    yes_details = f"{yes_pnl_str:<14} ({yes_info['wins']}W/{yes_info['losses']}L)"
    
    print(f"{m:<18} | {no_details:<26} | {yes_details:<26}")

print(f"{'-'*18} | {'-'*26} | {'-'*26}")
tot_no_pnl = sum([mb_no[m]['pnl'] for m in mb_no])
tot_yes_pnl = sum([mb_yes[m]['pnl'] for m in mb_yes])
tot_no_trades = sum([mb_no[m]['trades'] for m in mb_no])
tot_yes_trades = sum([mb_yes[m]['trades'] for m in mb_yes])

no_pnl_tot_str = f"{'+' if tot_no_pnl >= 0 else ''}INR {tot_no_pnl:,.2f}"
yes_pnl_tot_str = f"{'+' if tot_yes_pnl >= 0 else ''}INR {tot_yes_pnl:,.2f}"

print(f"{'TOTAL':<18} | {no_pnl_tot_str:<14} ({tot_no_trades} Trades) | {yes_pnl_tot_str:<14} ({tot_yes_trades} Trades)")
print("=======================================================\n")
