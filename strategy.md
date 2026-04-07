# Upstox Swing Trading Strategy Guide

This document outlines the core algorithmic trading rules, indicators, and risk management systems currently driving the application. The system is designed specifically for **3-7 day swing trading**, prioritizing mean reversion setups filtered by highly institutional macro indicators.

---

## 1. Core Technical Setup: Bollinger Bands Mean-Reversion
The core engine ignores late-stage momentum breakouts and instead focuses on catching the exact bottom of a temporary pullback within a larger uptrend.

* **Macro Trend Filter:** `Close > 50-day EMA`. The stock must fundamentally be in a macro uptrend. We do not buy falling knives.
* **Momentum Dip (Value):** `RSI(14) < 50`. The stock's short-term buying momentum must have cooled off.
* **The Entry Trigger:** The previous day's close must have touched or dipped beneath the **Lower Bollinger Band (20-day, 2 StdDev)**. The current day must bounce and close *above* the lower band. This signifies institutional dip-buyers stepping in.

---

## 2. Dynamic Profit Targets & Stop Losses (ATR)
Instead of using fixed percentages (which fail depending on whether a stock is naturally highly volatile or slow-moving), the system uses the **Average True Range (ATR)**. 
- ATR calculates exactly how much a stock naturally moves in a single day.
- Stop losses and targets are dynamically multiplied by the current stock's ATR, meaning wild stocks get wider buffers and slow stocks get tighter buffers.

---

## 3. Risk Profile Matrix
You can configure the algorithm's aggression inside `app/settings.py` via the `STRATEGY_RISK_PROFILE` variable.

| Profile | Entry Conditions | Target Multiplier | Stop-Loss Multiplier | Expected Target Duration |
| :--- | :--- | :--- | :--- | :--- |
| **SAFE** | Must bounce perfectly off Lower Bollinger while in a 50EMA uptrend with RSI < 50. | **2.0x ATR** (Fast Hit) | **1.5x ATR** (Tight Cut) | ~3 Trading Days |
| **MODERATE** | Follows Safe rules, but allows entering slightly early if the price is hovering near the lower band extreme. | **3.5x ATR** | **2.0x ATR** | ~5 Trading Days |
| **AGGRESSIVE** | Completely ignores the 50EMA trend rule and RSI rule. Buys purely on severe oversold statistical Bollinger Reversion logic. | **5.0x ATR** (Huge Swing) | **3.0x ATR** (Wide Buffer) | ~7 Trading Days |

---

## 4. Advanced Global Macro Filters
The strategy does not operate in a vacuum. Under the hood, a dedicated **Global Macro** module evaluates the broader financial ecosystem before giving a swing trade the green light. The global state is marked as **BEARISH** if any of these three conditions occur:
1. **Nifty 50 Downtrend:** The local Indian Nifty 50 index is actively trading below its 50-day EMA.
2. **Foreign Market Dump:** The American S&P 500 (`^GSPC`) crashed by more than `0.8%` overnight (setting the tone prior to NSE opening).
3. **AI News Sentiment:** A Natural Language Processing (NLP) AI engine analyzes the latest breaking global financial headlines. If the average linguistic polarity of the news is negative, it flags a global warning.

---

## 5. Dynamic Beta Protection Shield
Beta represents how volatile and sensitive a specific stock is compared to the overall Nifty 50 index. 
- The algorithm calculates the daily mathematical **Covariance** of the stock vs the Nifty 50 over the last 100 days.
- **The Override:** If the Global Macro filter calculates a **BEARISH** market:
    - **SAFE Profile:** Automatically blocks ALL buy calls globally to protect your capital.
    - **MODERATE Profile:** Blocks any stock with a Beta > 0.8. Allows low-beta/defensive stock buys (e.g., FMCG/Pharma).
    - **AGGRESSIVE Profile:** Blocks extreme tech/bank stocks (Beta > 1.2), but allows trading most standard assets.
