import pandas as pd
import numpy as np
from datetime import datetime, time
from app import settings

def apply_intraday_strategy(df: pd.DataFrame, macro_context: dict) -> dict:
    """
    Evaluates intraday data looking for ORB or VWAP crossovers.
    Returns standard signal response dictionary.
    """
    if df.empty or len(df) < 4:
        return {"signal": "HOLD", "reason": "Not enough intraday data."}
        
    # Calculate True Range and ATR (14 periods) for tight intraday stops/targets
    df['prev_close'] = df['close'].shift(1)
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['prev_close'])
    df['tr2'] = abs(df['low'] - df['prev_close'])
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['ATR'] = df['tr'].rolling(window=14, min_periods=1).mean()
    
    # Calculate VWAP
    df['Typical_Price'] = (df['high'] + df['low'] + df['close']) / 3
    df['Cum_Vol_Price'] = (df['Typical_Price'] * df['volume']).cumsum()
    df['Cum_Vol'] = df['volume'].cumsum()
    df['VWAP'] = df['Cum_Vol_Price'] / df['Cum_Vol']
    
    # Determine ORB (15-min = 09:15 to 09:30)
    # Filter rows before 09:30
    orb_end = pd.to_datetime('09:30').time()
    orb_data = df.loc[df['timestamp'].dt.time <= orb_end]
    
    if orb_data.empty:
        # Fallback to the first candle if market just opened or timings differ
        orb_high = df['high'].iloc[0]
        orb_low = df['low'].iloc[0]
    else:
        orb_high = orb_data['high'].max()
        orb_low = orb_data['low'].min()
        
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    current_time = latest['timestamp']
    # Hard stop near market close (e.g., 15:15)
    last_trading_time = pd.to_datetime('15:15').time()
    if current_time.time() >= last_trading_time:
         # Late in the day, don't trigger new setups
         return {
             "signal": "HOLD", 
             "confidence": 0.0,
             "entry_date": current_time.strftime("%Y-%m-%d %H:%M:%S"),
             "buying_price": latest['close'],
             "target_price": 0.0,
             "stop_loss": 0.0,
             "expected_target_date": "Today",
             "reason": "Too close to market close to initiate new trades."
         }
        
    # Nifty 50 macro filter from existing context
    nifty_trend = macro_context.get('local_nifty_trend', 'UNKNOWN')
    
    signal = 'HOLD'
    reason = 'No distinct intraday setup found.'
    target_price = 0.0
    stop_loss = 0.0
    confidence = 0.0
    entry_date = current_time.strftime("%Y-%m-%d %H:%M:%S")
    buying_price = latest['close']
    
    # Risk Profile Config
    risk_profile = getattr(settings, 'STRATEGY_RISK_PROFILE', 'SAFE')
    if risk_profile in ['SAFE', 'POSITIONAL', 'DIAMOND_HANDS']:
        target_multi = 1.5
        stop_multi = 1.0
        require_macro_alignment = True
    elif risk_profile == 'MODERATE':
        target_multi = 2.0
        stop_multi = 1.5
        require_macro_alignment = True
    else: # AGGRESSIVE
        target_multi = 2.5
        stop_multi = 1.5
        require_macro_alignment = False

    latest_close = latest['close']
    prev_close = prev['close']
    latest_vwap = latest['VWAP']
    prev_vwap = prev['VWAP']
    atr = latest['ATR']
    if pd.isna(atr) or atr == 0:
        atr = latest_close * 0.005 # Fallback 0.5% ATR if not enough data
    
    # Strategy 1: ORB Breakout
    # We only take ORB buys if Nifty50 is uptrend (unless aggressive), etc.
    if latest_close > orb_high and prev_close <= orb_high:
        if require_macro_alignment and nifty_trend == 'DOWNTREND':
             reason = 'HOLD: ORB Buy blocked by Nifty Downtrend.'
        else:
             signal = 'BUY'
             reason = f'[{risk_profile}] 15-Min ORB Breakout. Price cleared ORB High ({orb_high:.2f}).'
             target_price = latest_close + (atr * target_multi)
             stop_loss = orb_high - (atr * stop_multi)
             confidence = 85.0
             
    elif latest_close < orb_low and prev_close >= orb_low:
        if require_macro_alignment and nifty_trend == 'UPTREND':
             reason = 'HOLD: ORB Sell blocked by Nifty Uptrend.'
        else:
             signal = 'SELL'
             reason = f'[{risk_profile}] 15-Min ORB Breakdown. Price broke ORB Low ({orb_low:.2f}).'
             target_price = latest_close - (atr * target_multi)
             stop_loss = orb_low + (atr * stop_multi)
             confidence = 85.0

    # Strategy 2: VWAP Bounce/Crossover (only if ORB not triggered)
    if signal == 'HOLD':
        # VWAP Crossover Buy
        if prev_close < prev_vwap and latest_close > latest_vwap:
            if require_macro_alignment and nifty_trend == 'DOWNTREND':
                 reason = 'HOLD: VWAP Bullish crossover blocked by Nifty Downtrend.'
            else:
                 signal = 'BUY'
                 reason = f'[{risk_profile}] VWAP Bullish Crossover Setup.'
                 target_price = latest_close + (atr * target_multi)
                 stop_loss = latest_vwap - (atr * stop_multi)
                 confidence = 75.0
        # VWAP Crossover Sell (Shorting opportunity)
        elif prev_close > prev_vwap and latest_close < latest_vwap:
            if require_macro_alignment and nifty_trend == 'UPTREND':
                 reason = 'HOLD: VWAP Bearish crossover blocked by Nifty Uptrend.'
            else:
                 signal = 'SELL'
                 reason = f'[{risk_profile}] VWAP Bearish Crossover Setup.'
                 target_price = latest_close - (atr * target_multi)
                 stop_loss = latest_vwap + (atr * stop_multi)
                 confidence = 75.0

    # Ensure stop loss / limits don't break simple bounds
    if target_price > 0 and stop_loss > 0:
        if signal == 'BUY' and stop_loss > buying_price:
            stop_loss = buying_price * 0.99
        if signal == 'SELL' and stop_loss < buying_price:
            stop_loss = buying_price * 1.01

    return {
        "signal": signal,
        "confidence": round(confidence, 2),
        "entry_date": entry_date,
        "buying_price": round(buying_price, 2),
        "target_price": round(target_price, 2),
        "stop_loss": round(stop_loss, 2),
        "expected_target_date": "Today",
        "reason": reason
    }
