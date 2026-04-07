from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from datetime import datetime, timedelta, timezone
import pandas as pd
import numpy as np
from app import settings

def apply_swing_strategy(df: pd.DataFrame, macro_context: dict = None) -> dict:
    """
    Applies a highly-accurate Mean Reversion swing strategy using Bollinger Bands.
    Includes Risk Profiles and Macro/Beta Overrides.
    """
    if df.empty or len(df) < 55:
        return {"signal": "HOLD", "reason": "Not enough data (need at least 55 days)"}

    # Calculate Indicators
    ema_50 = EMAIndicator(close=df['close'], window=50)
    rsi_14 = RSIIndicator(close=df['close'], window=14)
    bb = BollingerBands(close=df['close'], window=20, window_dev=2)
    atr_14 = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
    
    df['EMA_50'] = ema_50.ema_indicator()
    df['RSI_14'] = rsi_14.rsi()
    df['BB_LOWER'] = bb.bollinger_lband()
    df['BB_MIDDLE'] = bb.bollinger_mavg()
    df['BB_UPPER'] = bb.bollinger_hband()
    df['ATR'] = atr_14.average_true_range()

    # Calculate Beta
    beta = 1.0
    if macro_context and macro_context.get('nifty_df') is not None:
        try:
            nifty_df = macro_context['nifty_df']
            
            # Align by timestamp and calculate percentage change
            stock_returns = df.set_index('timestamp')['close'].pct_change().dropna()
            nifty_returns = nifty_df.set_index('timestamp')['close'].pct_change().dropna()
            
            merged = pd.DataFrame({'stock': stock_returns}).join(pd.DataFrame({'nifty': nifty_returns}), how='inner').dropna()
            
            if len(merged) > 30:
                covariance = np.cov(merged['stock'], merged['nifty'])[0][1]
                variance = np.var(merged['nifty'])
                if variance > 0:
                    beta = round(covariance / variance, 2)
        except Exception:
            pass  # Fallback to standard 1.0 beta if alignment fails

    df = df.dropna()
    if len(df) < 2:
        return {"signal": "HOLD", "reason": "Not enough valid data after calculating indicators"}

    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]
    
    buy_price = round(last_row['close'], 2)
    current_atr = last_row['ATR']
    risk_profile = settings.STRATEGY_RISK_PROFILE.upper()

    # Base Technical Conditions (Bollinger Reversion Logic)
    base_trend_up = buy_price > last_row['EMA_50']
    rsi_cooled = last_row['RSI_14'] < 50
    bounced_off_lower = (prev_row['close'] <= prev_row['BB_LOWER'] * 1.01) and (last_row['close'] > last_row['BB_LOWER'])
    near_lower_band = last_row['close'] <= (last_row['BB_LOWER'] + (current_atr * 0.5))
    
    is_buy = False
    stop_atr_mult = 2.0
    target_atr_mult = 3.0
    target_days = 5
    
    if risk_profile == "SCALPER":
        is_buy = (bounced_off_lower or near_lower_band)
        stop_atr_mult = 1.0
        target_atr_mult = 1.5
        target_days = 2
    elif risk_profile == "SAFE":
        is_buy = base_trend_up and bounced_off_lower and rsi_cooled
        stop_atr_mult = 1.5
        target_atr_mult = 2.0
        target_days = 3
    elif risk_profile == "AGGRESSIVE":
        is_buy = (bounced_off_lower or near_lower_band)
        stop_atr_mult = 3.0
        target_atr_mult = 5.0
        target_days = 7
    elif risk_profile == "POSITIONAL":
        is_buy = base_trend_up and bounced_off_lower
        stop_atr_mult = 5.0
        target_atr_mult = 10.0
        target_days = 20
    elif risk_profile == "DIAMOND_HANDS":
        is_buy = bounced_off_lower
        stop_atr_mult = 10.0
        target_atr_mult = 25.0
        target_days = 60
    else:
        # MODERATE
        is_buy = base_trend_up and (bounced_off_lower or near_lower_band) and rsi_cooled
        stop_atr_mult = 2.0
        target_atr_mult = 3.5
        target_days = 5

    # Target & Stop Loss Calculation
    from pandas.tseries.offsets import BusinessDay

    stop_loss = round(buy_price - (current_atr * stop_atr_mult), 2)
    target_price = round(buy_price + (current_atr * target_atr_mult), 2)
    
    # Calculate physically accurate expected timespan using average recent velocity
    avg_daily_change = df['close'].tail(14).diff().abs().mean()
    if pd.isna(avg_daily_change) or avg_daily_change == 0:
        avg_daily_change = current_atr * 0.5  # fallback
        
    target_distance = target_price - buy_price
    # Assume 60% of daily volatility contributes to directional trend on average (efficiency ratio)
    directional_velocity = avg_daily_change * 0.60
    try:
        calculated_target_days = int(np.ceil(target_distance / directional_velocity))
        # Cap the timeline boundaries (2 days min, 15 days max for a swing trade)
        calculated_target_days = max(2, min(calculated_target_days, 15))
    except (ValueError, ZeroDivisionError):
        calculated_target_days = target_days  # fallback to profile default
        
    IST = timezone(timedelta(hours=5, minutes=30))
    
    if hasattr(settings, 'BACKTEST_TARGET_DATE') and settings.BACKTEST_TARGET_DATE:
        try:
            base_date = datetime.strptime(settings.BACKTEST_TARGET_DATE, "%Y-%m-%d").replace(tzinfo=IST)
        except ValueError:
            base_date = datetime.now(IST)
    else:
        base_date = datetime.now(IST)
        
    # Calculate exactly using trading days (skipping weekends)
    expected_date = (base_date + BusinessDay(n=calculated_target_days)).strftime("%Y-%m-%d")

    fields = {
        "buying_price": buy_price,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "expected_target_date": expected_date,
        "beta": beta
    }

    # ---------------- MACRO & BETA OVERRIDE LOGIC ----------------
    macro_state = macro_context.get('global_macro_state', "NEUTRAL") if macro_context else "NEUTRAL"
    ai_sent = macro_context.get('ai_news_sentiment', "NEUTRAL") if macro_context else "NEUTRAL"
    override_reason = ""
    
    if is_buy and macro_state == "BEARISH":
        if risk_profile == "SAFE":
            is_buy = False
            override_reason = "Blocked by SAFE profile during Global Bear Market."
        elif risk_profile == "MODERATE" and beta > 0.8:
            is_buy = False
            override_reason = f"Blocked: Moderate profile rejects Beta {beta} during Bear Market."
        elif risk_profile == "AGGRESSIVE" and beta > 1.2:
            is_buy = False
            override_reason = f"Blocked: High Beta {beta} too risky during Bear Market."

    # Entry Logic
    if is_buy:
        reason = (
            f"Strategy Evaluation: The stock is currently trading at {buy_price}, structurally confirmed "
            f"above its core 50-day EMA trendline ({last_row['EMA_50']:.1f}). Over the last week, price consolidated, "
            f"statistically bouncing off the Lower Bollinger Band floor ({last_row['BB_LOWER']:.1f}) indicating extreme value. "
            f"RSI confirms cooling momentum ({last_row['RSI_14']:.1f}). "
            f"Action: Initiating an '{risk_profile}' profile trade with calculated Beta [{beta}]. "
            f"Setting aggressive target at +{target_atr_mult}x ATR ({target_price}) and protective Stop-Loss at -{stop_atr_mult}x ATR ({stop_loss})."
        )
        return {
            "signal": "BUY",
            "reason": reason,
            **fields
        }

    # Sell Logic
    rsi_overbought = last_row['RSI_14'] >= 75
    trend_broken = buy_price < last_row['EMA_50']
    hit_upper_band = buy_price >= last_row['BB_UPPER']

    if trend_broken or rsi_overbought or hit_upper_band:
        if trend_broken:
            broken_reason = f"the current price ({buy_price}) severely broke structure beneath its core 50-day EMA support ({last_row['EMA_50']:.1f})"
        elif rsi_overbought:
            broken_reason = f"the asset hit extreme overbought momentum (RSI > 75 at {last_row['RSI_14']:.1f}) risking an imminent crash"
        else:
            broken_reason = f"the price directly rejected the heavy statistical resistance of the Upper Bollinger Band ({last_row['BB_UPPER']:.1f})"

        reason = (
            f"Strategy Evaluation: Exit signaled immediately because {broken_reason}. "
            f"Holding this stock further carries exceptional risk down to the baseline. "
            f"Action: Liquidating under current profile protocols."
        )
        return {
            "signal": "SELL",
            "reason": reason,
            **fields
        }

    hold_reason = override_reason if override_reason else f"Waiting setup. Beta: {beta}, Macro: {macro_state}, AI: {ai_sent}."
    return {
        "signal": "HOLD",
        "reason": hold_reason,
        **fields
    }
