from flask import Flask, request, jsonify
from flasgger import Swagger, swag_from
from app.data_fetcher import fetch_historical_data, fetch_intraday_data
from app.strategy import apply_swing_strategy
from app.intraday_strategy import apply_intraday_strategy
from app.telegram_notifier import send_telegram_message
from apscheduler.schedulers.background import BackgroundScheduler
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

def _get_instruments_from_request():
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
    return sector_param, instruments

def _generate_calls_data():
    sector_param, instruments = _get_instruments_from_request()
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
                "name": instrument_name,
                "instrument": instrument,
                "signal": signal_data.get("signal", "ERROR"),
                "confidence": signal_data.get("confidence", 0.0),
                "entry_date": signal_data.get("entry_date", ""),
                "buying_price": signal_data.get("buying_price", 0.0),
                "target_price": signal_data.get("target_price", 0.0),
                "stop_loss": signal_data.get("stop_loss", 0.0),
                "expected_target_date": signal_data.get("expected_target_date", ""),
                "reason": signal_data.get("reason", "Unknown")
            })
        except Exception as e:
            results.append({
                "name": instrument,
                "instrument": instrument,
                "signal": "ERROR",
                "confidence": 0.0,
                "entry_date": "",
                "buying_price": 0.0,
                "target_price": 0.0,
                "stop_loss": 0.0,
                "expected_target_date": "",
                "reason": str(e)
            })
            
    logger.info(f"Analyzed {len(instruments)} instruments. Discovered {len([r for r in results if r['signal'] in ['BUY', 'SELL']])} active trade setups.")
            
    # Always sort by name so the output order is consistent (alphabetical) for all endpoints
    results.sort(key=lambda x: x.get("name", x.get("instrument", "")))
    
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
                        "name": instrument_name,
                        "instrument": instrument,
                        "signal": signal,
                        "confidence": signal_data.get("confidence", 0.0),
                        "entry_date": signal_data.get("entry_date", ""),
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

def _generate_intraday_calls_data():
    sector_param, instruments = _get_instruments_from_request()
    logger.info(f"Initiating INTRADAY sequence for sector param: {sector_param}")
    
    macro_context = get_macro_state()
    results = []
    for instrument in instruments:
        try:
            df = fetch_intraday_data(instrument, interval="1minute")
            signal_data = apply_intraday_strategy(df, macro_context)
            
            instrument_name = INSTRUMENT_NAMES.get(instrument, instrument)
            results.append({
                "name": instrument_name,
                "instrument": instrument,
                "signal": signal_data.get("signal", "ERROR"),
                "confidence": signal_data.get("confidence", 0.0),
                "entry_date": signal_data.get("entry_date", ""),
                "buying_price": signal_data.get("buying_price", 0.0),
                "target_price": signal_data.get("target_price", 0.0),
                "stop_loss": signal_data.get("stop_loss", 0.0),
                "expected_target_date": signal_data.get("expected_target_date", ""),
                "reason": signal_data.get("reason", "Unknown")
            })
        except Exception as e:
            results.append({
                "name": instrument,
                "instrument": instrument,
                "signal": "ERROR",
                "confidence": 0.0,
                "entry_date": "",
                "buying_price": 0.0,
                "target_price": 0.0,
                "stop_loss": 0.0,
                "expected_target_date": "",
                "reason": str(e)
            })
            
    logger.info(f"Analyzed {len(instruments)} intraday instruments. Discovered {len([r for r in results if r['signal'] in ['BUY', 'SELL']])} active trade setups.")
    results.sort(key=lambda x: x.get("name", x.get("instrument", "")))
    return {"macro_context": macro_context, "results": results, "sector_analyzed": sector_param}

@app.route('/intraday/calls/buy', methods=['GET'])
@swag_from(get_swagger_schema("Get ONLY INTRADAY BUY calls", "Analyzes live intraday data via Upstox API using VWAP/ORB Strategy."))
def get_intraday_buy_calls():
    try:
        data = _generate_intraday_calls_data()
    except InvalidSectorError as e:
        return jsonify({"error": str(e)}), 400
    buy_calls = [r for r in data["results"] if r.get('signal') == 'BUY']
    return jsonify({
        "macro_evaluation": format_macro_summary(data["macro_context"], data["sector_analyzed"]),
        "results": buy_calls
    })

@app.route('/intraday/calls/sell', methods=['GET'])
@swag_from(get_swagger_schema("Get ONLY INTRADAY SELL calls", "Analyzes live intraday data via Upstox API using VWAP/ORB Strategy."))
def get_intraday_sell_calls():
    try:
        data = _generate_intraday_calls_data()
    except InvalidSectorError as e:
        return jsonify({"error": str(e)}), 400
    sell_calls = [r for r in data["results"] if r.get('signal') == 'SELL']
    return jsonify({
        "macro_evaluation": format_macro_summary(data["macro_context"], data["sector_analyzed"]),
        "results": sell_calls
    })

@app.route('/intraday/calls/all-sectors', methods=['GET'])
@swag_from({
    "tags": ["Trading"],
    "summary": "Get INTRADAY calls across all sectors",
    "description": "Scans every defined sector and returns a dictionary grouped by sector featuring active BUY/SELL intraday signals."
})
def get_intraday_all_sectors_calls():
    macro_context = get_macro_state()
    summary = {}
    seen_instruments = set()
    for sector_name, instruments in SECTORS.items():
        results = []
        for instrument in instruments:
            if instrument in seen_instruments:
                continue
            seen_instruments.add(instrument)
            try:
                df = fetch_intraday_data(instrument, interval="1minute")
                signal_data = apply_intraday_strategy(df, macro_context)
                
                signal = signal_data.get("signal", "ERROR")
                if signal in ['BUY', 'SELL']:
                    instrument_name = INSTRUMENT_NAMES.get(instrument, instrument)
                    results.append({
                        "name": instrument_name,
                        "instrument": instrument,
                        "signal": signal,
                        "confidence": signal_data.get("confidence", 0.0),
                        "entry_date": signal_data.get("entry_date", ""),
                        "buying_price": signal_data.get("buying_price", 0.0),
                        "target_price": signal_data.get("target_price", 0.0),
                        "stop_loss": signal_data.get("stop_loss", 0.0),
                        "expected_target_date": signal_data.get("expected_target_date", ""),
                        "reason": signal_data.get("reason", "Unknown")
                    })
            except Exception:
                pass
        summary[sector_name] = results
        
    logger.info("Successfully fetched intraday calls across all isolated sectors.")
    return jsonify({
        "macro_evaluation": format_macro_summary(macro_context, "ALL SECTORS SCAN"),
        "summary": summary
    })


def scheduled_intraday_job():
    logger.info(f"Executing automated {settings.AUTOMATION_INTRADAY_TIME} Intraday Sweep for Telegram bot.")
    macro_context = get_macro_state()
    
    # We want to scan all sectors as requested
    target_sectors = list(SECTORS.keys())
    instruments_to_scan = []
    
    seen = set()
    for sector in target_sectors:
        if sector in SECTORS:
            for inst in SECTORS[sector]:
                if inst not in seen:
                    seen.add(inst)
                    instruments_to_scan.append(inst)
                    
    results = []
    for instrument in instruments_to_scan:
        try:
            df = fetch_intraday_data(instrument, interval="1minute")
            signal_data = apply_intraday_strategy(df, macro_context)
            signal = signal_data.get("signal", "HOLD")
            
            if signal in ['BUY', 'SELL']:
                inst_name = INSTRUMENT_NAMES.get(instrument, instrument)
                import html
                results.append({
                    "name": html.escape(str(inst_name)),
                    "instrument": html.escape(str(instrument)),
                    "signal": html.escape(str(signal)),
                    "confidence": signal_data.get("confidence", 0.0),
                    "entry_date": html.escape(str(signal_data.get("entry_date", ""))),
                    "buying_price": signal_data.get("buying_price", 0.0),
                    "target_price": signal_data.get("target_price", 0.0),
                    "stop_loss": signal_data.get("stop_loss", 0.0),
                    "expected_target_date": html.escape(str(signal_data.get("expected_target_date", ""))),
                    "reason": html.escape(str(signal_data.get("reason", "Unknown")))
                })
        except Exception as e:
            logger.error(f"Error scanning {instrument} in scheduled job: {e}")
            
    if results:
        results.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)
        top_results = results[:3]
        formatted_messages = []
        for r in top_results:
            msg = (
                f"<b>{r['signal']}</b>: {r['name']} ({r['instrument']})\n"
                f"Confidence: {r['confidence']}%\n"
                f"Entry Date: {r['entry_date']}\n"
                f"Entry Price: ₹{r['buying_price']}\n"
                f"Target: ₹{r['target_price']}\n"
                f"Stop Loss: ₹{r['stop_loss']}\n"
                f"Expected Target Date: {r['expected_target_date']}\n"
                f"Reason: {r['reason']}"
            )
            formatted_messages.append(msg)
            
        message = f"🚨 <b>Live Intraday Setups Found ({settings.AUTOMATION_INTRADAY_TIME}) - TOP 3</b> 🚨\n\n" + "\n\n".join(formatted_messages)
        send_telegram_message(message)
    else:
        logger.info("Automation finished: 0 setups found, skipping Telegram message.")

def scheduled_swing_job():
    logger.info(f"Executing automated {settings.AUTOMATION_SWING_TIME} Swing Sweep for Telegram bot.")
    macro_context = get_macro_state()
    
    # We want to scan all sectors as requested
    target_sectors = list(SECTORS.keys())
    instruments_to_scan = []
    
    seen = set()
    for sector in target_sectors:
        if sector in SECTORS:
            for inst in SECTORS[sector]:
                if inst not in seen:
                    seen.add(inst)
                    instruments_to_scan.append(inst)
                    
    results = []
    for instrument in instruments_to_scan:
        try:
            df = fetch_historical_data(instrument, days_back=settings.HISTORICAL_DATA_DAYS)
            signal_data = apply_swing_strategy(df, macro_context)
            signal = signal_data.get("signal", "HOLD")
            
            if signal == 'BUY':
                inst_name = INSTRUMENT_NAMES.get(instrument, instrument)
                import html
                results.append({
                    "name": html.escape(str(inst_name)),
                    "instrument": html.escape(str(instrument)),
                    "signal": html.escape(str(signal)),
                    "confidence": signal_data.get("confidence", 0.0),
                    "entry_date": html.escape(str(signal_data.get("entry_date", ""))),
                    "buying_price": signal_data.get("buying_price", 0.0),
                    "target_price": signal_data.get("target_price", 0.0),
                    "stop_loss": signal_data.get("stop_loss", 0.0),
                    "expected_target_date": html.escape(str(signal_data.get("expected_target_date", ""))),
                    "reason": html.escape(str(signal_data.get("reason", "Unknown")))
                })
        except Exception as e:
            logger.error(f"Error scanning {instrument} in swing scheduled job: {e}")
            
    if results:
        results.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)
        top_results = results[:3]
        formatted_messages = []
        for r in top_results:
            msg = (
                f"<b>{r['signal']}</b>: {r['name']} ({r['instrument']})\n"
                f"Confidence: {r['confidence']}%\n"
                f"Entry Date: {r['entry_date']}\n"
                f"Entry Price: ₹{r['buying_price']}\n"
                f"Target: ₹{r['target_price']}\n"
                f"Stop Loss: ₹{r['stop_loss']}\n"
                f"Expected Target Date: {r['expected_target_date']}\n"
                f"Reason: {r['reason']}"
            )
            formatted_messages.append(msg)
            
        message = f"📊 <b>Swing Setups Found ({settings.AUTOMATION_SWING_TIME}) - TOP 3</b> 📊\n\n" + "\n\n".join(formatted_messages)
        send_telegram_message(message)
    else:
        logger.info("Swing automation finished: 0 setups found, skipping Telegram message.")

# Initialize APScheduler globally
scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

swing_h, swing_m = settings.AUTOMATION_SWING_TIME.split(":")
intra_h, intra_m = settings.AUTOMATION_INTRADAY_TIME.split(":")

scheduler.add_job(
    scheduled_swing_job, 
    'cron', 
    day_of_week='mon-fri', 
    hour=int(swing_h), 
    minute=int(swing_m)
)

end_h = min(23, int(intra_h) + 4)
scheduler.add_job(
    scheduled_intraday_job, 
    'cron', 
    day_of_week='mon-fri', 
    hour=f'{int(intra_h)}-{end_h}', 
    minute=int(intra_m)
)
scheduler.start()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
