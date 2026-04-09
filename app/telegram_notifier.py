import os
import requests
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

def send_telegram_message(message: str) -> bool:
    """
    Sends a text message to the configured Telegram bot.
    Requires 'telegram_bot_token' and 'telegram_chat_id' in the .env file.
    """
    load_dotenv()
    
    token = os.getenv("telegram_bot_token")
    chat_id = os.getenv("telegram_chat_id")
    
    if not token or not chat_id:
        logger.error("Missing telegram_bot_token or telegram_chat_id in environment variables.")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        chunks = []
        current_chunk = ""
        for part in message.split("\n\n"):
            if len(current_chunk) + len(part) + 2 > 4000:
                chunks.append(current_chunk)
                current_chunk = part
            else:
                current_chunk = current_chunk + ("\n\n" + part if current_chunk else part)
        if current_chunk:
            chunks.append(current_chunk)
            
        for chunk in chunks:
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
        logger.info(f"Successfully dispatched Telegram notification in {len(chunks)} chunks.")
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")
        return False
