from binance.exceptions import BinanceAPIException # Third party 
from urllib.request import urlopen
from config import client
from utility import get_url
from enums import EARLIEST_DATE
import pandas as pd
import json
import csv
import os

# Big picture: Trying to work out when the best time to buy after listing is
# Also the percentage of newly listed coins which 2x+ from their 2w ATL - if it takes more than 6 months, then put it in fails
# Also roughly when that surge happens (the week the first 2x occurs)
# Also percentage of newly listed coins which fail.

def init_scan_binance(save_path, tradingpair, mode):

	os.mkdir(save_path)
	with open(save_path + f"{tradingpair}_symbol_listing_gains_{mode}.json", 'w') as js, open(save_path + f"{tradingpair}_symbol_listing_stats_{mode}.csv", 'w') as f:
		json.dump({}, js, indent=4)
		csv_writer = csv.writer(f)
		csv_writer.writerow(["symbol", "success", "2w_start_price", "2x_date", "ATL", "ATH", "listing_date"])


def get_USD_symbols(*modes, tradingpair="USD"):
	'''Finds all COINUSDT symbols if they exist, else gets COINBUSD symbols'''

	symbols = set()
	for exchange_info in [urlopen(url).read() for url in [get_url(mode) for mode in modes]]:
		exchange_info = json.loads(exchange_info)
		prev_coin = str
		for symbol_info in exchange_info["symbols"]:
			if symbol_info["baseAsset"] != prev_coin:
				if tradingpair == "USD" and (symbol_info["quoteAsset"] == "USDT" or symbol_info["quoteAsset"] == "BUSD"):
					symbols.add(symbol_info["symbol"])
				elif tradingpair == "BTC" and symbol_info["quoteAsset"] == "BTC":
					symbols.add(symbol_info["symbol"])
				elif tradingpair == "ETH" and symbol_info["quoteAsset"] == "ETH":
					symbols.add(symbol_info["symbol"])
				prev_coin = symbol_info["baseAsset"]					
	return symbols


def anaylse_klines(symbol, klines, gains_data, stat_row, mode):

	atl = [int(i) for i in stat_row["ATL"].split("|")]
	ath = [int(i) for i in stat_row["ATH"].split("|")]
	for kline_1w in klines:
		gains_since_start = int((float(kline_1w[4]) / stat_row["2w_start_price"]) * 100)
		loss_since_start = int((float(kline_1w[3]) / stat_row["2w_start_price"]) * 100)
		if (gains_since_start >= 200 and not int(stat_row["2x_date"][0])):
			stat_row["2x_date"] = f"{kline_1w[0]}|{int((int(kline_1w[0]) - stat_row['listing_date'])/604800000)}"
			stat_row["success"] = True if mode == "short_term" else False
		if (loss_since_start < atl[-1]):
			atl = [kline_1w[0], loss_since_start]
		if (gains_since_start > ath[-1]):
			ath = [kline_1w[0], gains_since_start]
		gains_data[symbol].append(gains_since_start)
	stat_row["ATL"] = f"{atl[0]}|{atl[-1]}"
	stat_row["ATH"] = f"{ath[0]}|{ath[-1]}"


def scan_binance_listing_trends(symbols, tradingpair, save_path, mode="short_term"):
	'''mode either short_term or long_term'''

	if not os.path.exists(save_path):
		init_scan_binance(save_path, tradingpair, mode)
	data_path = save_path + f"{tradingpair}_symbol_listing_gains_{mode}.json"
	stats_path = save_path + f"{tradingpair}_symbol_listing_stats_{mode}.csv"
	with open(data_path, 'r') as js:
		listing_data = json.load(js)
	listing_stats = pd.read_csv(stats_path, index_col= 0)

	# update symbols already in database if needed
	for symbol in symbols.intersection(set(listing_data.keys())):
		print(f"Seen symbol: {symbol}")
		weeks_until_6months = 26 - len(listing_data[symbol]) + 1 # Example, 26 - 16 = 10, meaning 10 weeks + 1 incomplete week
		if weeks_until_6months > 0 or mode == "long_term":
			until = weeks_until_6months if mode == "short_term" else 1000
			stat_row = listing_stats.loc[symbol].to_dict()
			weekly_klines = client.get_historical_klines(symbol, "1w", listing_data["latest_weekly_UTS"])
			listing_data[symbol].pop(-1) # because latest entry is incomplete
			anaylse_klines(symbol, weekly_klines[:until], listing_data, stat_row, mode)
			listing_stats.loc[symbol] = [val for val in stat_row.values()] # need to get symbol out in front

	# loop through new symbols which haven't been added to database
	current_weekly_UTS = 0
	stats_rows = []
	for symbol in list(symbols.difference(set(listing_data.keys())))[:5]:
		print(f"symbol: {symbol}")
		try:
			weekly_klines = client.get_historical_klines(symbol, "1w", EARLIEST_DATE)
			if (len(weekly_klines) < 2):
				continue
			if not current_weekly_UTS:
				current_weekly_UTS = weekly_klines[-1][0]
				listing_data["latest_weekly_UTS"] = current_weekly_UTS
			stat_row = {"symbol":symbol,
						"success":False,
						"2w_start_price":float(weekly_klines[1][3]),
						"2x_date":"0|0",
						"ATL":"0|0",
						"ATH":"0|0",
						"listing_date":int(weekly_klines[0][0])}
			until = 27 if mode == "short_term" else 1000
			listing_data[symbol] = [100] # 100% start percentage
			anaylse_klines(symbol, weekly_klines[2:until], listing_data, stat_row, mode)
			stats_rows.append(stat_row)
		except BinanceAPIException:
			continue
	
	if stats_rows:
		listing_stats.reset_index(level=0, inplace=True)
		listing_stats = listing_stats.append(stats_rows)
		listing_stats.set_index("symbol", inplace=True)
	listing_stats.to_csv(stats_path, mode='w', index=True)
	with open(data_path, 'w') as jf:
		json.dump(listing_data, jf, indent=4)


def graph():
	# TODO use the data from database
	pass


if __name__ == "__main__":

	save_path = os.path.dirname(os.path.realpath(__file__)) + f"/coindata/binance_scan/"
	symbols = get_USD_symbols("spot", tradingpair="USD")
	scan_binance_listing_trends(symbols, "USD", save_path)
			