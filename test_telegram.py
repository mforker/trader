import os
import sys
from dotenv import load_dotenv

# Add app to path so we can import telegram_notifier securely
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.telegram_notifier import send_telegram_message

if __name__ == "__main__":
    load_dotenv()
    print("Testing Telegram Dispatcher...")
    success = send_telegram_message("🔔 <b>Trader App Test</b> 🔔\n\nYour automated ID binding was successful. You will receive intraday calls here at 10:00 AM!")
    if success:
        print("Test dispatched! Check your phone.")
    else:
        print("Failed to dispatch.")
