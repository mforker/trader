import pandas as pd
import urllib.request
import gzip
import json
import os

print("Fetching official Upstox instruments database...")
url = 'https://assets.upstox.com/market-quote/instruments/exchange/NSE.csv.gz'
response = urllib.request.urlopen(url)
with gzip.GzipFile(fileobj=response) as f:
    upstox_df = pd.read_csv(f)

# Define our dynamic NSE indices
INDEX_URLS = {
    "NIFTY50": "ind_nifty50list.csv",
    "NIFTYBANK": "ind_niftybanklist.csv",
    "NIFTYIT": "ind_niftyitlist.csv",
    "NIFTYPHARMA": "ind_niftypharmalist.csv",
    "NIFTYFMCG": "ind_niftyfmcglist.csv",
    "NIFTYAUTO": "ind_niftyautolist.csv",
    "NIFTYREALTY": "ind_niftyrealtylist.csv",
    "NIFTYPSUBANK": "ind_niftypsubanklist.csv",
    "NIFTYPVTBANK": "ind_niftypvtbanklist.csv",
    "NIFTY100_LARGECAP": "ind_nifty100list.csv",
    "NIFTYMIDCAP150": "ind_niftymidcap150list.csv",
    "NIFTYSMALLCAP250": "ind_niftysmallcap250list.csv"
}

CUSTOM_SECTORS = {
    "CHEMICALS": ["SRF", "PIIND", "TATACHEM", "AARTIIND", "DEEPAKNTR", "UPL", "NAVINFLUOR"],
    "CEMENT": ["ULTRACEMCO", "SHREECEM", "GRASIM", "AMBUJACEM", "ACC", "DALBHARAT", "RAMCOCEM"]
}

SECTORS = {}
BASE_URL = "https://archives.nseindia.com/content/indices/"

print("Contacting NSE Archives...")
for sector_name, csv_file in INDEX_URLS.items():
    print(f"Downloading NSE live constituents for {sector_name}...")
    try:
        index_df = pd.read_csv(BASE_URL + csv_file)
        symbols = index_df['Symbol'].tolist()
        SECTORS[sector_name] = symbols
    except Exception as e:
        print(f"Error fetching {sector_name}: {e}")

# Merge Custom Sectors
for sector_name, symbols in CUSTOM_SECTORS.items():
    SECTORS[sector_name] = symbols

sector_instruments = {}
instrument_names = {}

for sector, symbols in SECTORS.items():
    sector_instruments[sector] = []
    found_count = 0
    for symbol in symbols:
        # Match where tradingsymbol equals our target symbol in EQ segment
        match = upstox_df[(upstox_df['tradingsymbol'] == symbol) & (upstox_df['instrument_type'] == 'EQUITY')]
        if not match.empty:
            instrument_key = match.iloc[0]['instrument_key']
            sector_instruments[sector].append(instrument_key)
            instrument_names[instrument_key] = symbol
            found_count += 1
            
    print(f"Mapped {found_count}/{len(symbols)} Upstox instruments for {sector}")

file_path = os.path.join(os.path.dirname(__file__), 'sectors.py')
with open(file_path, 'w') as f:
    f.write('"""Pre-defined sectors mapping to Upstox Instrument Keys directly compiled from NSE India"""\n\n')
    f.write('SECTORS = \\\n')
    f.write(json.dumps(sector_instruments, indent=4))
    f.write('\n\nINSTRUMENT_NAMES = \\\n')
    f.write(json.dumps(instrument_names, indent=4))

print("Successfully generated sectors.py!")
