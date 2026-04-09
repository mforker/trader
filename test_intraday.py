from main import app
import json

def run_tests():
    with app.test_client() as client:
        print("Testing Intraday BUY calls for sector BANK...")
        response = client.get('/intraday/calls/buy?sector=BANK')
        
        print(f"\nStatus Code: {response.status_code}")
        
        data = response.json
        if data:
            results = data.get("results", [])
            print(f"\nFound {len(results)} Buy calls for BANK sector.")
            
            # Print at most the first 2 calls to avoid giant output logs
            if results:
                print("\nSample Results:")
                print(json.dumps(results[:2], indent=2))
            
            # If no buy calls, let's try the ALL sectors endpoint to see if we get anything
            if not results:
                print("\nNo BUY calls found. This is common if the market is closed or Nifty is in a downtrend.")
                print("Let's test the ALL-SECTORS endpoint just to verify functionality.")
                all_resp = client.get('/intraday/calls/all-sectors')
                print(f"All Sectors Status: {all_resp.status_code}")
                # We won't print the huge ALL sectors output, just verify it didn't throw a 500 server error
        else:
            print("Response had no JSON data.")

if __name__ == "__main__":
    run_tests()
