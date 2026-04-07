from flask import Flask, request, jsonify
from flasgger import Swagger, swag_from
from app.data_fetcher import fetch_historical_data
from app.strategy import apply_swing_strategy
from app.sectors import SECTORS, INSTRUMENT_NAMES
from app.global_macro import get_macro_state
from app import settings
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler

# Configure Rotating File Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        RotatingFileHandler("trader.log", maxBytes=5000000, backupCount=2),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
# Keep JSON payload fields exactly in the order we dictionary mapped them (don't alphabetize)
app.json.sort_keys = False

# Configure Flasgger
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/"
}
swagger = Swagger(app, config=swagger_config, template={"info": {"title": "Upstox Swing Trading API", "version": "1.0"}})

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "message": "Welcome to the Upstox Swing Trading API",
        "documentation": "/apidocs/"
    })

def _generate_calls_data():
    sector_param = request.args.get('sector')
    instruments_param = request.args.get('instruments')
    
    if not sector_param and not instruments_param:
        sector_param = settings.DEFAULT_SECTOR
        
    if sector_param and sector_param.upper() == "ALL":
        instruments = []
        for s in SECTORS.values():
            instruments.extend(s)
    elif sector_param and sector_param.upper() in SECTORS:
        instruments = SECTORS[sector_param.upper()]
    else:
        instruments = [i.strip() for i in instruments_param.split(',')]
    logger.info(f"Initiating sequence for sector param: {sector_param}")
    
    macro_context = get_macro_state()
    results = []
    for instrument in instruments:
        try:
            # Fetch historical data using configured days
            df = fetch_historical_data(instrument, days_back=settings.HISTORICAL_DATA_DAYS)
            
            # Apply our 3-7 day swing strategy with macro context
            signal_data = apply_swing_strategy(df, macro_context)
            
            instrument_name = INSTRUMENT_NAMES.get(instrument, instrument)
            results.append({
                "instrument": instrument,
                "name": instrument_name,
                "signal": signal_data.get("signal", "ERROR"),
                "buying_price": signal_data.get("buying_price", 0.0),
                "target_price": signal_data.get("target_price", 0.0),
                "stop_loss": signal_data.get("stop_loss", 0.0),
                "expected_target_date": signal_data.get("expected_target_date", ""),
                "reason": signal_data.get("reason", "Unknown")
            })
        except Exception as e:
            results.append({
                "instrument": instrument,
                "signal": "ERROR",
                "reason": str(e),
                "last_price": None
            })
            
    logger.info(f"Analyzed {len(instruments)} instruments. Discovered {len([r for r in results if r['signal'] in ['BUY', 'SELL']])} active trade setups.")
            
    return {"macro_context": macro_context, "results": results, "sector_analyzed": sector_param}

def format_macro_summary(macro_context, sector_analyzed=None):
    return {
        "sector_analyzed": sector_analyzed or "UNKNOWN",
        "active_strategy": "Bollinger Bands Mean-Reversion (ATR Scaled)",
        "risk_profile": settings.STRATEGY_RISK_PROFILE,
        "nifty_50_trend": macro_context.get('local_nifty_trend', 'UNKNOWN'),
        "sp500_overnight_trend": f"{macro_context.get('foreign_sp500_trend', 'UNKNOWN')} ({macro_context.get('foreign_sp500_pct', 0.0):.2f}%)",
        "ai_news_sentiment": macro_context.get('ai_news_sentiment', 'UNKNOWN'),
        "news_articles_analyzed": macro_context.get('news_articles_analyzed', 0),
        "global_macro_state": macro_context.get('global_macro_state', 'UNKNOWN'),
        "top_headlines": macro_context.get('headlines', [])
    }

def get_swagger_schema(title, description):
    return {
        "tags": ["Trading"],
        "summary": title,
        "description": description,
        "parameters": [
            {
                "name": "sector",
                "in": "query",
                "type": "string",
                "required": False,
                "description": f"Sector to scan. Available: BANK, ENERGY, IT, AUTO, FMCG, PHARMA, MEDIA, PSU, CHEMICALS, CEMENT, REALTY. Default is {settings.DEFAULT_SECTOR}."
            },
            {
                "name": "instruments",
                "in": "query",
                "type": "string",
                "required": False,
                "description": "Comma-separated list of Upstox instrument keys. Default is NSE_EQ|INE002A01018 (Reliance Industries).",
                "default": "NSE_EQ|INE002A01018"
            }
        ],
        "responses": {
            200: {
                "description": "A successful response containing signals for each instrument",
                "examples": {
                    "application/json": {
                        "results": [
                            {
                                "instrument": "NSE_EQ|INE002A01018",
                                "name": "RELIANCE",
                                "signal": "BUY",
                                "buying_price": 2855.5,
                                "target_price": 2985.0,
                                "stop_loss": 2790.0,
                                "expected_target_date": "2026-04-12",
                                "reason": "[SAFE] Buy Setup Triggered. Target determined by 2.0x ATR."
                            }
                        ]
                    }
                }
            }
        }
    }

@app.route('/calls/buy', methods=['GET'])
@swag_from(get_swagger_schema("Get ONLY BUY calls", "Analyzes historical data via Upstox API using Advanced Swing Strategy. Returns exclusively elements with signal BUY."))
def get_buy_calls():
    data = _generate_calls_data()
    buy_calls = [r for r in data["results"] if r.get('signal') == 'BUY']
    return jsonify({
        "macro_evaluation": format_macro_summary(data["macro_context"], data["sector_analyzed"]),
        "results": buy_calls
    })

@app.route('/calls/sell', methods=['GET'])
@swag_from(get_swagger_schema("Get ONLY SELL calls", "Analyzes historical data via Upstox API using Advanced Swing Strategy. Returns exclusively elements with signal SELL."))
def get_sell_calls():
    data = _generate_calls_data()
    sell_calls = [r for r in data["results"] if r.get('signal') == 'SELL']
    return jsonify({
        "macro_evaluation": format_macro_summary(data["macro_context"], data["sector_analyzed"]),
        "results": sell_calls
    })

@app.route('/calls/all-sectors', methods=['GET'])
@swag_from({
    "tags": ["Trading"],
    "summary": "Get BUY/SELL calls across all sectors",
    "description": "Scans every defined sector and returns a dictionary grouped by sector featuring active BUY/SELL signals.",
    "responses": {
        200: {
            "description": "A successful response mapping sectors to signals"
        }
    }
})
def get_all_sectors_calls():
    macro_context = get_macro_state()
    summary = {}
    for sector_name, instruments in SECTORS.items():
        results = []
        for instrument in instruments:
            try:
                df = fetch_historical_data(instrument, days_back=settings.HISTORICAL_DATA_DAYS)
                signal_data = apply_swing_strategy(df, macro_context)
                
                signal = signal_data.get("signal", "ERROR")
                if signal in ['BUY', 'SELL']:
                    instrument_name = INSTRUMENT_NAMES.get(instrument, instrument)
                    results.append({
                        "instrument": instrument,
                        "name": instrument_name,
                        "signal": signal,
                        "buying_price": signal_data.get("buying_price", 0.0),
                        "target_price": signal_data.get("target_price", 0.0),
                        "stop_loss": signal_data.get("stop_loss", 0.0),
                        "expected_target_date": signal_data.get("expected_target_date", ""),
                        "reason": signal_data.get("reason", "Unknown")
                    })
            except Exception:
                pass
        summary[sector_name] = results
        
    logger.info("Successfully fetched calls across all isolated sectors.")
    return jsonify({
        "macro_evaluation": format_macro_summary(macro_context, "ALL SECTORS SCAN"),
        "summary": summary
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
