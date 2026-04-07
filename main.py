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

class InvalidSectorError(Exception):
    """Raised when an unrecognisable sector or no input is provided."""
    pass

def _generate_calls_data():
    sector_param = request.args.get('sector')
    instruments_param = request.args.get('instruments')
    
    if not sector_param and not instruments_param:
        sector_param = settings.DEFAULT_SECTOR
        
    # Alias map for natural language inputs that don't substring-match NSE key names
    SECTOR_ALIASES = {
        # Private Bank
        "PRIVATEBANK": "NIFTYPVTBANK",
        "PVTBANK": "NIFTYPVTBANK",
        "PRIVATEBANKINDEX": "NIFTYPVTBANK",
        "PRIVATE": "NIFTYPVTBANK",
        "PRIVBANK": "NIFTYPVTBANK",
        # PSU Bank
        "PSUBANK": "NIFTYPSUBANK",
        "PSU": "NIFTYPSUBANK",
        "PUBLICSECTORBANK": "NIFTYPSUBANK",
        "PUBLICBANK": "NIFTYPSUBANK",
        "GOVTBANK": "NIFTYPSUBANK",
        "STATEBANK": "NIFTYPSUBANK",
        # Banking (general)
        "BANK": "NIFTYBANK",
        "BANKING": "NIFTYBANK",
        "BANKINDEX": "NIFTYBANK",
        "BANKNIFTY": "NIFTYBANK",
        "BANKS": "NIFTYBANK",
        # IT
        "IT": "NIFTYIT",
        "TECH": "NIFTYIT",
        "TECHNOLOGY": "NIFTYIT",
        "INFORMATIONTECHNOLOGY": "NIFTYIT",
        "INFOTECH": "NIFTYIT",
        "SOFTWARE": "NIFTYIT",
        "TECHINDEX": "NIFTYIT",
        # Pharma
        "PHARMA": "NIFTYPHARMA",
        "PHARMACEUTICAL": "NIFTYPHARMA",
        "PHARMACEUTICALS": "NIFTYPHARMA",
        "HEALTHCARE": "NIFTYPHARMA",
        "HEALTH": "NIFTYPHARMA",
        "MEDICINE": "NIFTYPHARMA",
        # FMCG
        "FMCG": "NIFTYFMCG",
        "CONSUMERGOOD": "NIFTYFMCG",
        "CONSUMERGOODS": "NIFTYFMCG",
        "CONSUMER": "NIFTYFMCG",
        "FASTMOVING": "NIFTYFMCG",
        "STAPLES": "NIFTYFMCG",
        # Auto
        "AUTO": "NIFTYAUTO",
        "AUTOMOBILE": "NIFTYAUTO",
        "AUTOMOBILES": "NIFTYAUTO",
        "AUTOMOTIVE": "NIFTYAUTO",
        "VEHICLES": "NIFTYAUTO",
        "CAR": "NIFTYAUTO",
        "EV": "NIFTYAUTO",
        # Realty
        "REALTY": "NIFTYREALTY",
        "REAL": "NIFTYREALTY",
        "REALESTATE": "NIFTYREALTY",
        "REALTYINDEX": "NIFTYREALTY",
        "PROPERTY": "NIFTYREALTY",
        "HOUSING": "NIFTYREALTY",
        # Smallcap
        "SMALLCAP": "NIFTYSMALLCAP250",
        "SMALLCAP250": "NIFTYSMALLCAP250",
        "SMALL": "NIFTYSMALLCAP250",
        "SMALLCAPINDEX": "NIFTYSMALLCAP250",
        # Midcap
        "MIDCAP": "NIFTYMIDCAP150",
        "MIDCAP150": "NIFTYMIDCAP150",
        "MID": "NIFTYMIDCAP150",
        "MIDCAPINDEX": "NIFTYMIDCAP150",
        # Largecap
        "LARGECAP": "NIFTY100_LARGECAP",
        "LARGE": "NIFTY100_LARGECAP",
        "NIFTY100": "NIFTY100_LARGECAP",
        "LARGECAPINDEX": "NIFTY100_LARGECAP",
        "TOP100": "NIFTY100_LARGECAP",
        # Nifty 50
        "NIFTY": "NIFTY50",
        "NIFTY50INDEX": "NIFTY50",
        "TOP50": "NIFTY50",
        "N50": "NIFTY50",
        # Chemicals
        "CHEMICAL": "CHEMICALS",
        "CHEM": "CHEMICALS",
        "SPECIALTY": "CHEMICALS",
        # Cement
        "CEMENT": "CEMENT",
        "INFRASTRUCTURE": "CEMENT",
        "INFRA": "CEMENT",
        "CONSTRUCTION": "CEMENT",
    }

    if sector_param and sector_param.upper() == "ALL":
        seen = set()
        instruments = []
        for s in SECTORS.values():
            for i in s:
                if i not in seen:
                    seen.add(i)
                    instruments.append(i)
    elif sector_param:
        sector_key = sector_param.upper()
        # 1. Check alias map first
        if sector_key in SECTOR_ALIASES:
            sector_key = SECTOR_ALIASES[sector_key]
        # 2. Exact match
        if sector_key not in SECTORS:
            # 3. Fuzzy substring match as last resort
            matches = [k for k in SECTORS.keys() if sector_key in k]
            sector_key = matches[0] if matches else None
        
        if sector_key and sector_key in SECTORS:
            instruments = SECTORS[sector_key]
            sector_param = sector_key  # normalize for logging
        elif instruments_param:
            instruments = [i.strip() for i in instruments_param.split(',')]
        else:
            available = sorted(list(SECTORS.keys()) + ["ALL"])
            raise InvalidSectorError(
                f"Unknown sector '{sector_param}'. "
                f"Try one of: {', '.join(available)}. "
                f"Or use common names like 'bank', 'it', 'pharma', 'fmcg', 'auto', 'smallcap', 'midcap', 'largecap', 'privatebank', 'psubank', 'realty'."
            )
    elif instruments_param:
        instruments = [i.strip() for i in instruments_param.split(',')]
    else:
        raise InvalidSectorError(
            "No sector or instruments provided. "
            "Add ?sector=NIFTY50 or ?sector=bank to your request."
        )
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
    try:
        data = _generate_calls_data()
    except InvalidSectorError as e:
        return jsonify({"error": str(e)}), 400
    buy_calls = [r for r in data["results"] if r.get('signal') == 'BUY']
    return jsonify({
        "macro_evaluation": format_macro_summary(data["macro_context"], data["sector_analyzed"]),
        "results": buy_calls
    })

@app.route('/calls/sell', methods=['GET'])
@swag_from(get_swagger_schema("Get ONLY SELL calls", "Analyzes historical data via Upstox API using Advanced Swing Strategy. Returns exclusively elements with signal SELL."))
def get_sell_calls():
    try:
        data = _generate_calls_data()
    except InvalidSectorError as e:
        return jsonify({"error": str(e)}), 400
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
    seen_instruments = set()  # Deduplicate stocks that appear in multiple indices
    for sector_name, instruments in SECTORS.items():
        results = []
        for instrument in instruments:
            if instrument in seen_instruments:
                continue  # Skip — already analyzed in a prior sector
            seen_instruments.add(instrument)
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
