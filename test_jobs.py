from main import scheduled_swing_job, app
from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv()
    with app.app_context():
        print("Testing scheduled_swing_job directly...")
        scheduled_swing_job()
        print("Done.")
