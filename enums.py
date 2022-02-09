from datetime import datetime
INTERVALS = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '3h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M'] # All avaliable intervals on binance
EARLIEST_DATE = "1 Jan, 2017" # Date binance started
DEFAULT_TIMEFRAMES = ['1w', '3d', '1d', '12h', '4h', '1h']
DEFAULT_THRESHOLD = 15
SYMBOLS_URL1 = "https://api.binance.com/api/v3/exchangeInfo"
SYMBOLS_URL2 = "https://fapi.binance.com/fapi/v1/exchangeInfo"
SYMBOLS_URL3 = "https://dapi.binance.com/dapi/v1/exchangeInfo"
BEAR_MARKETS = [[datetime(2017, 12, 26), datetime(2019, 4, 2)],
                [datetime(2019, 8, 7), datetime(2020, 4, 23)]]
BULL_MARKETS = [[datetime(2017, 1, 1), datetime(2017, 12, 26)],
                [datetime(2019, 4, 2), datetime(2019, 8, 7)],
                [datetime(2020, 4, 23), datetime.now()]]
