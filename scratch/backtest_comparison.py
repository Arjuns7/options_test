import json
import math
import datetime
import pandas as pd

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

# --- Expiry Date Calculation ---
def get_expiry_date(date_str):
    # Standard Thursday weekly expiry simulation
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    # Find next Thursday (weekday = 3)
    days_ahead = 3 - dt.weekday()
    if days_ahead <= 0: # Already Thursday or Friday, go to next week
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
# Filter for last 6 months (approx Jan 14, 2026 to July 13, 2026)
df = df[df["date"] >= "2026-01-14"].copy()
df['datetime'] = pd.to_datetime(df['date'])
df = df.sort_values(by=['date', 'tickIdx']).reset_index(drop=True)

# Run Backtest
def run_backtest(use_filter=False):
    # Calculate EMA on global series for proper warm up
    df['EMA_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['EMA_20'] = df['close'].ewm(span=20, adjust=False).mean()
    
    capital = 100000.0
    active_trade = None
    trades = []
    
    for i in range(2, len(df)):
        tick = df.iloc[i]
        date_str = tick['date']
        tick_idx = tick['tickIdx']
        spot = tick['close']
        
        # 1. Manage Active Trade
        if active_trade:
            # Time to expiry (in years)
            expiry_dt = get_expiry_date(date_str)
            days_diff = (expiry_dt - datetime.datetime.strptime(date_str, "%Y-%m-%d")).days
            hours_left = 15.5 - (9.25 + tick_idx * 0.25)
            T_tick = max(0.0001, (days_diff + hours_left / 24) / 365.25)
            
            # Fetch current premium
            current_premium = black_scholes(
                active_trade['type'], 
                spot, 
                active_trade['strike'], 
                T_tick, 
                tick['r'], 
                tick['iv'] / 100
            )
            
            # Exit conditions
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
            elif tick_idx == 24: # 3:15 PM Square off
                close_trade = True
                status = 'TIME_EXIT'
                
            if close_trade:
                pnl = (exit_premium - active_trade['entry_premium']) * active_trade['qty']
                trades.append({
                    "date": active_trade['entry_date'],
                    "type": active_trade['type'],
                    "strike": active_trade['strike'],
                    "entry_spot": active_trade['entry_spot'],
                    "exit_spot": spot,
                    "entry_premium": round(active_trade['entry_premium'], 2),
                    "exit_premium": round(exit_premium, 2),
                    "pnl": round(pnl, 2),
                    "status": status
                })
                active_trade = None
                
        # 2. Check for Crossover Signals
        else:
            prev_tick1 = df.iloc[i-1]
            prev_tick2 = df.iloc[i-2]
            
            # Ensure we are looking at the same day's crossover
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
                
            if signal != 'NONE' and tick_idx < 24: # Enter only before square off
                # If filter is enabled:
                # BULLISH -> close must be above 20 EMA
                # BEARISH -> close must be below 20 EMA
                if use_filter:
                    ema20 = prev_tick1['EMA_20']
                    if signal == 'BULLISH' and close1 <= ema20:
                        continue
                    if signal == 'BEARISH' and close1 >= ema20:
                        continue
                        
                option_type = 'C' if signal == 'BULLISH' else 'P'
                atm_strike = round(spot / 50) * 50
                strike = atm_strike - 50 if option_type == 'C' else atm_strike + 50
                
                # Fetch entry premium
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
                    "qty": 150 # 2 Lots
                }
                
    return trades

trades_no_filter = run_backtest(use_filter=False)
trades_with_filter = run_backtest(use_filter=True)

# Calculate stats
def get_stats(trades):
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    net_pnl = sum([t['pnl'] for t in trades])
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0
    return {
        "count": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 2),
        "net_pnl": round(net_pnl, 2)
    }

s_no = get_stats(trades_no_filter)
s_yes = get_stats(trades_with_filter)

print("\n==========================================")
print("   6-MONTH BACKTEST COMPARISON REPORT     ")
print("   (Nifty 15-Min EMA Crossover Strategy)  ")
print("==========================================")
print(f"Dataset Range: January 14, 2026 to July 13, 2026")
print(f"Trade Lot Size: 150 units (2 Lots)\n")

print(f"1. WITHOUT 20 EMA Trend Filter:")
print(f"   * Total Trades: {s_no['count']}")
print(f"   * Wins: {s_no['wins']} | Losses: {s_no['losses']}")
print(f"   * Win Rate: {s_no['win_rate']}%")
print(f"   * Net P&L: {'+' if s_no['net_pnl'] >= 0 else ''}INR {s_no['net_pnl']:,}")

print(f"\n2. WITH 20 EMA Trend Filter:")
print(f"   * Total Trades: {s_yes['count']}")
print(f"   * Wins: {s_yes['wins']} | Losses: {s_yes['losses']}")
print(f"   * Win Rate: {s_yes['win_rate']}%")
print(f"   * Net P&L: {'+' if s_yes['net_pnl'] >= 0 else ''}INR {s_yes['net_pnl']:,}")

print("\n==========================================")
print("               ANALYSIS                   ")
print("==========================================")
pnl_diff = s_yes['net_pnl'] - s_no['net_pnl']
trades_avoided = s_no['count'] - s_yes['count']
print(f"* Filter blocked {trades_avoided} whipsaw/counter-trend trades.")
print(f"* Win Rate changed by {round(s_yes['win_rate'] - s_no['win_rate'], 2)}% points.")
print(f"* Net P&L Difference: {'+' if pnl_diff >= 0 else ''}INR {pnl_diff:,.2f}")
print("==========================================\n")
