import os
import requests
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("telegram_bot_token")
if not token:
    print("No telegram_bot_token found.")
    exit(1)

url = f"https://api.telegram.org/bot{token}/getUpdates"
print(f"Fetching updates from: {url}")
response = requests.get(url)
data = response.json()

if not data.get("ok"):
    print("Error getting updates:", data)
    exit(1)

results = data.get("result", [])
if not results:
    print("No messages found! Please send a message to the bot @personaltraderappbot first.")
else:
    # Get the latest message
    latest = results[-1]
    if "message" in latest:
        chat_id = latest["message"]["chat"]["id"]
        username = latest["message"]["from"].get("username", "Unknown")
        print(f"Found Chat ID: {chat_id} from user: @{username}")
        
        # Append to .env automatically
        with open(".env", "a") as f:
            f.write(f"\ntelegram_chat_id = \"{chat_id}\"\n")
        print("Successfully appended telegram_chat_id to .env file!")
    else:
        print("Latest update does not contain a message:", latest)
