"""
Settings configuration for Upstox Swing Trading App
"""

# Default sector to generate calls for if none is selected
# Available Sector Options (Automatically pulled from NSE):
# - NIFTY50
# - NIFTYBANK
# - NIFTYIT
# - NIFTYPHARMA
# - NIFTYFMCG
# - NIFTYAUTO
# - NIFTYREALTY
# - NIFTYPSUBANK
# - NIFTYPVTBANK
# - NIFTY100_LARGECAP
# - NIFTYMIDCAP150
# - NIFTYSMALLCAP250
# - CHEMICALS (Custom Segment)
# - CEMENT (Custom Segment)
# - ALL
DEFAULT_SECTOR = "ALL"

# Number of days of historical data to process for technical analysis
# We need at least 100 calendar days to securely calculate a 50-day trading EMA.
HISTORICAL_DATA_DAYS = 180

# Risk Profile for target and stop-loss calculations.
# Options: SCALPER, SAFE, MODERATE, AGGRESSIVE, POSITIONAL, DIAMOND_HANDS
STRATEGY_RISK_PROFILE = "POSITIONAL"

# Backtesting Global Controls
# Set to None for Live Market Data
# Set to a point-in-time date string (e.g. "2026-03-01") to run a historical mathematical backtest
BACKTEST_TARGET_DATE = None
