import os
import time
import pandas as pd
import numpy as np
import threading
import urllib.request
import urllib.parse
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from fyers_apiv3 import fyersModel

# --- Telegram Credentials ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }).encode("utf-8")
    
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req) as res:
            res.read()
    except Exception as e:
        print(f"⚠️ Failed to send Telegram alert: {e}")

# --- Configuration ---
CLIENT_ID = os.environ.get("FYERS_CLIENT_ID", "YOUR_FYERS_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("FYERS_ACCESS_TOKEN", "YOUR_FYERS_ACCESS_TOKEN") # Generated daily
INDEX_SYMBOL = "NSE:NIFTY50-INDEX"        # Symbol for Nifty 50 Spot
EMA_PERIOD = 9
LOTS_MULTIPLIER = 2                       # Traded quantity multiplier
STOP_LOSS_PCT = 0.20                      # 20% Stop Loss
TARGET_PROFIT_PCT = 0.30                  # 30% Target Profit

# --- Initialize Fyers Client ---
fyers = fyersModel.FyersModel(client_id=CLIENT_ID, token=ACCESS_TOKEN, log_path=os.getcwd())

# --- State Variables ---
active_trade = None

# --- Background HTTP Health Check Server (Required for Railway Deploy) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        status_msg = f"OK - Fyers Paper Trading Active. Active Trade: {active_trade is not None}"
        self.wfile.write(status_msg.encode('utf-8'))
        
    def log_message(self, format, *args):
        # Suppress logging HTTP requests to clean stdout logs
        return

def start_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🏥 Health check server listening on port {port}...")
    server.serve_forever()

# Start the health check server thread
threading.Thread(target=start_health_check_server, daemon=True).start()

# --- Helper Functions ---
def get_live_nifty_candles():
    """Fetch recent historical 15-minute candles to calculate the EMA."""
    data = {
        "symbol": INDEX_SYMBOL,
        "resolution": "15",
        "date_format": "1",
        "range_from": datetime.today().strftime('%Y-%m-%d'),
        "range_to": datetime.today().strftime('%Y-%m-%d'),
        "cont_flag": "1"
    }
    try:
        response = fyers.history(data=data)
        if response and response.get('s') == 'ok':
            # Parse candles: [Timestamp, Open, High, Low, Close, Volume]
            df = pd.DataFrame(response['candles'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
            return df
    except Exception as e:
        print(f"Error fetching candles: {e}")
    return None

def calculate_ema(df, period):
    df['EMA'] = df['close'].ewm(span=period, adjust=False).mean()
    return df

def check_crossover(df):
    if len(df) < 3:
        return 'NONE'
    
    prev_close1 = df['close'].iloc[-2]
    prev_ema1 = df['EMA'].iloc[-2]
    
    prev_close2 = df['close'].iloc[-3]
    prev_ema2 = df['EMA'].iloc[-3]
    
    if prev_close1 > prev_ema1 and prev_close2 <= prev_ema2:
        return 'BULLISH'
    elif prev_close1 < prev_ema1 and prev_close2 >= prev_ema2:
        return 'BEARISH'
    
    return 'NONE'

def log_virtual_trade(trade_details):
    """Write paper trading logs to a local CSV file."""
    log_file = "fyers_paper_trades.csv"
    df = pd.DataFrame([trade_details])
    if not os.path.isfile(log_file):
        df.to_csv(log_file, index=False)
    else:
        df.to_csv(log_file, mode='a', header=False, index=False)
    print(f"📄 Virtual Trade Logged: {trade_details}")

# --- Main Trading Loop ---
print("🚀 Fyers Nifty 15-Min EMA Paper Trading Engine Started...")
send_telegram_message("🚀 *Fyers 15-Min EMA Paper Trading Engine Started* successfully on Railway!")
while True:
    try:
        df = get_live_nifty_candles()
        if df is not None:
            df = calculate_ema(df, EMA_PERIOD)
            current_spot = df['close'].iloc[-1]
            signal = check_crossover(df)
            
            # 1. Manage Active Paper Trade
            if active_trade:
                spot_change = current_spot - active_trade['entry_spot']
                delta = 0.55 if active_trade['option_type'] == 'CE' else -0.55
                estimated_premium_change = spot_change * delta
                current_premium = max(1.0, active_trade['entry_premium'] + estimated_premium_change)
                
                # Check limits
                pnl = (current_premium - active_trade['entry_premium']) * active_trade['qty']
                sl_limit = active_trade['entry_premium'] * (1 - STOP_LOSS_PCT)
                tp_limit = active_trade['entry_premium'] * (1 + TARGET_PROFIT_PCT)
                
                close_reason = None
                if current_premium <= sl_limit:
                    close_reason = "STOP_LOSS_HIT"
                elif current_premium >= tp_limit:
                    close_reason = "TARGET_PROFIT_HIT"
                elif datetime.now().hour == 15 and datetime.now().minute >= 15:
                    close_reason = "DAILY_SQUARE_OFF"
                
                if close_reason:
                    active_trade['exit_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    active_trade['exit_spot'] = current_spot
                    active_trade['exit_premium'] = round(current_premium, 2)
                    active_trade['pnl'] = round(pnl, 2)
                    active_trade['status'] = close_reason
                    log_virtual_trade(active_trade)
                    
                    # Send exit Telegram alert
                    msg = (f"🎯 *[PAPER TRADE EXIT - {close_reason}]*\n"
                           f"*Index*: NIFTY 50\n"
                           f"*Contract*: {active_trade['strike']} {active_trade['option_type']}\n"
                           f"*Spot Price*: ₹{current_spot}\n"
                           f"*Exit Premium*: ₹{round(current_premium, 2)}\n"
                           f"*Net P&L*: **₹{round(pnl, 2)}** (Simulated)")
                    send_telegram_message(msg)
                    
                    active_trade = None
            
            # 2. Check for Crossover Signals
            elif signal != 'NONE' and datetime.now().hour < 15:
                option_type = 'CE' if signal == 'BULLISH' else 'PE'
                atm_strike = round(current_spot / 50) * 50
                strike = atm_strike - 50 if option_type == 'CE' else atm_strike + 50
                entry_premium = 100.0  
                
                active_trade = {
                    "entry_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "option_type": option_type,
                    "strike": strike,
                    "qty": 75 * LOTS_MULTIPLIER, 
                    "entry_spot": current_spot,
                    "entry_premium": entry_premium,
                    "exit_time": None,
                    "exit_spot": None,
                    "exit_premium": None,
                    "pnl": 0.0,
                    "status": "ACTIVE"
                }
                print(f"🔔 Signal Triggered: {signal}! Entered virtual trade: Buy Nifty {strike} {option_type} at Spot {current_spot}")
                
                # Send entry Telegram alert
                msg = (f"🔔 *[PAPER TRADE ENTRY]*\n"
                       f"*Index*: NIFTY 50\n"
                       f"*Signal*: {signal} 15-Min Cross\n"
                       f"*Contract*: BUY {strike} {option_type} ({LOTS_MULTIPLIER} Lots)\n"
                       f"*Spot Price*: ₹{current_spot}\n"
                       f"*Est. Premium*: ₹{entry_premium}")
                send_telegram_message(msg)
                
        time.sleep(30)
    except Exception as e:
        print(f"⚠️ Loop Error: {e}")
        time.sleep(10)
