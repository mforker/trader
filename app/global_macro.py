import yfinance as yf
from textblob import TextBlob
from datetime import datetime, timedelta
from app.data_fetcher import fetch_historical_data
from app import settings

def get_foreign_index_state():
    try:
        # Fetch S&P 500
        sp500 = yf.Ticker("^GSPC")
        
        if hasattr(settings, 'BACKTEST_TARGET_DATE') and settings.BACKTEST_TARGET_DATE:
            end_date = datetime.strptime(settings.BACKTEST_TARGET_DATE, "%Y-%m-%d") + timedelta(days=1)
            start_date = end_date - timedelta(days=10)
            hist = sp500.history(start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
        else:
            hist = sp500.history(period="5d")
            
        if len(hist) < 2:
            return "NEUTRAL", 0.0
            
        last_close = hist['Close'].iloc[-1]
        prev_close = hist['Close'].iloc[-2]
        pct_change = ((last_close - prev_close) / prev_close) * 100
        
        if pct_change < -0.8:
            return "BEARISH", pct_change
        elif pct_change > 0.8:
            return "BULLISH", pct_change
        else:
            return "NEUTRAL", pct_change
    except:
        return "NEUTRAL", 0.0

def get_global_news_sentiment():
    if hasattr(settings, 'BACKTEST_TARGET_DATE') and settings.BACKTEST_TARGET_DATE:
        return "NEUTRAL", 0.0, ["[BACKTEST MODE] AI NLP Sentiment disabled to prevent cheating with future news."], 0
        
    try:
        sp500 = yf.Ticker("^GSPC")
        news = sp500.news
        if not news:
            return "NEUTRAL", 0.0, [], 0
            
        total_polarity = 0
        valid_headlines = 0
        headlines = []
        
        for item in news:
            # yfinance nests article data inside item['content'] in recent versions
            content = item.get('content', item)  # fallback to item itself for older versions
            title = content.get('title', '')
            summary = content.get('summary', '')
            
            # Combine title + summary for richer NLP signal
            text_to_analyze = f"{title}. {summary}".strip('. ')
            if text_to_analyze:
                blob = TextBlob(text_to_analyze)
                total_polarity += blob.sentiment.polarity
                valid_headlines += 1
                if title:
                    headlines.append(title)
                
        if valid_headlines == 0:
            return "NEUTRAL", 0.0, [], 0
            
        avg_polarity = total_polarity / valid_headlines
        
        # Polarity ranges from -1.0 to 1.0 (approximating thresholds for finance)
        if avg_polarity < -0.05:
            return "NEGATIVE", avg_polarity, headlines[:5], valid_headlines
        elif avg_polarity > 0.05:
            return "POSITIVE", avg_polarity, headlines[:5], valid_headlines
        else:
            return "NEUTRAL", avg_polarity, headlines[:5], valid_headlines
    except Exception as e:
        return "NEUTRAL", 0.0, [f"News fetch error: {str(e)}"], 0

def get_macro_state():
    """
    Returns a unified dictionary of market condition flags and reference dataframes.
    """
    # 1. Fetch Nifty 50 for local macro and beta calculations
    try:
        nifty_df = fetch_historical_data("NSE_INDEX|Nifty 50", days_back=settings.HISTORICAL_DATA_DAYS)
        if not nifty_df.empty and len(nifty_df) > 50:
            # Quick check on Nifty 50 50-EMA
            nifty_50_ema = nifty_df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
            nifty_last_close = nifty_df['close'].iloc[-1]
            local_trend = "BULLISH" if nifty_last_close > nifty_50_ema else "BEARISH"
        else:
            local_trend = "NEUTRAL"
            nifty_df = None
    except:
        local_trend = "NEUTRAL"
        nifty_df = None

    # 2. Fetch Foreign Markets (S&P 500)
    foreign_trend, foreign_pct = get_foreign_index_state()
    
    # 3. NLP News Sentiment
    news_sentiment, sentiment_score, headlines, articles_analyzed = get_global_news_sentiment()
    
    # 4. Aggregate Global View
    if local_trend == "BEARISH" or foreign_trend == "BEARISH" or news_sentiment == "NEGATIVE":
        global_state = "BEARISH"
    elif local_trend == "BULLISH" and foreign_trend == "BULLISH":
        global_state = "BULLISH"
    else:
        global_state = "NEUTRAL"

    return {
        "nifty_df": nifty_df,
        "local_nifty_trend": local_trend,
        "foreign_sp500_trend": foreign_trend,
        "foreign_sp500_pct": foreign_pct,
        "ai_news_sentiment": news_sentiment,
        "ai_sentiment_score": sentiment_score,
        "news_articles_analyzed": articles_analyzed,
        "headlines": headlines,
        "global_macro_state": global_state
    }
