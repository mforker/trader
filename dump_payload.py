import os, sys, json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import scheduled_swing_job
import app.telegram_notifier
import requests

old_post = requests.post

def mock_post(url, json=None, **kwargs):
    with open("telegram_payload.txt", "w", encoding="utf-8") as f:
        f.write(json.get("text", ""))
    print("Payload written to telegram_payload.txt")
    return old_post(url, json=json, **kwargs)

requests.post = mock_post

if __name__ == "__main__":
    scheduled_swing_job()
