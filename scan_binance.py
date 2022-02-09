from binance.exceptions import BinanceAPIException # Third party 
from urllib.request import urlopen
from config import client
from utility import get_url
from datetime import datetime
from enums import EARLIEST_DATE
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import json
import csv
import os

def init_scan_binance(tradingpair, mode):

	save_path = os.path.dirname(os.path.realpath(__file__)) + f"/coindata/binance_scan/"
	if not os.path.exists(save_path):
		os.mkdir(save_path)
	with open(save_path + f"{tradingpair}_symbol_listing_gains_{mode}.json", 'w') as js, open(save_path + f"{tradingpair}_symbol_listing_stats_{mode}.csv", 'w') as f:
		json.dump({}, js, indent=4)
		csv_writer = csv.writer(f)
		csv_writer.writerow(["symbol", "success", "2w_start_price", "week_of_2x", "ATL", "week_of_ATL", "ATH", "week_of_ATH", "listing_date"])


def get_file_path(file, tradingpair, mode):
	save_path = os.path.dirname(os.path.realpath(__file__)) + f"/coindata/binance_scan/"
	if file == 'gains':
		return f"{save_path}{tradingpair}_symbol_listing_gains_{mode}.json"
	elif file == 'stats':
		return f"{save_path}{tradingpair}_symbol_listing_stats_{mode}.csv"
	elif file == 'graph_gains':
		return f"{save_path}{tradingpair}_symbol_gains_graph_{mode}.png"
	elif file == 'graph_dates':
		return f"{save_path}{tradingpair}_symbol_dates_graph_{mode}.png"		


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
	'''Start price is the ATL at 2weeks. This function finds the first week where the price is double the start price.
	In short_term mode, the scan will stop once 6 months of price action has passed, otherwise it will keep going.'''

	atl = int(stat_row["ATL"])
	ath = int(stat_row["ATH"])
	for kline_1w in klines:
		gains_since_start = int((float(kline_1w[4]) / stat_row["2w_start_price"]) * 100)
		loss_since_start = int((float(kline_1w[3]) / stat_row["2w_start_price"]) * 100)
		week_since_listing = int((int(kline_1w[0]) - stat_row['listing_date'])/604800000)
		if (gains_since_start >= 200 and not int(stat_row["week_of_2x"])):
			if mode == "short_term" and week_since_listing <= 26:
				stat_row["week_of_2x"] = week_since_listing
				stat_row["success"] = True
			elif mode == "long_term":
				stat_row["week_of_2x"] = week_since_listing
				stat_row["success"] = True
		if (loss_since_start < atl):
			stat_row['week_of_ATL'] = week_since_listing
			stat_row["ATL"] = loss_since_start
			atl = loss_since_start
		if (gains_since_start > ath):
			stat_row['week_of_ATH'] = week_since_listing
			stat_row["ATH"] = gains_since_start
			ath = gains_since_start
		gains_data[symbol].append(gains_since_start)


def scan_binance_listing_trends(symbols, tradingpair, mode="short_term"):
	'''Retreive data from binance for each symbol and performs basic analysis. Stores data in db. 
	mode either short_term (only looks at first 6 months of data) or long_term'''

	init_scan_binance(tradingpair, mode)
	data_path = get_file_path('gains', tradingpair, mode)
	stats_path = get_file_path('stats', tradingpair, mode)
	with open(data_path, 'r') as js:
		listing_data = json.load(js)
	listing_stats = pd.read_csv(stats_path, index_col= 0)
	klines = client.get_historical_klines('BTCUSDT', "1w", "1 Jan, 2022")
	listing_data["latest_weekly_UTS"] = klines[-1][0]

	# update symbols already in database if needed
	for symbol in symbols.intersection(set(listing_data.keys())):
		weeks_until_6months = 26 - len(listing_data[symbol]) + 1 # Example, 26 - 16 = 10, meaning 10 weeks + 1 incomplete week
		if weeks_until_6months > 0 or mode == "long_term":
			until = weeks_until_6months if mode == "short_term" else 1000
			stat_row = listing_stats.loc[symbol].to_dict()
			weekly_klines = client.get_historical_klines(symbol, "1w", listing_data["latest_weekly_UTS"])
			listing_data[symbol].pop(-1) # because latest entry is incomplete
			anaylse_klines(symbol, weekly_klines[:until], listing_data, stat_row, mode)
			listing_stats.loc[symbol] = [val for val in stat_row.values()] # need to get symbol out in front

	# loop through new symbols which haven't been added to database
	stats_rows = []
	for symbol in symbols.difference(set(listing_data.keys())):
		try:
			weekly_klines = client.get_historical_klines(symbol, "1w", EARLIEST_DATE)
			if (len(weekly_klines) < 2):
				continue
			stat_row = {"symbol":symbol,
						"success":False,
						"2w_start_price":float(weekly_klines[1][3]),
						"week_of_2x":"0",
						"ATL":"100",
						"week_of_ATL":"0",
						"ATH":"100",
						"week_of_ATH":"0",
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


def graph(tradingpair, mode="short_term"):

	data_path = get_file_path('gains', tradingpair, mode)
	stats_path = get_file_path('stats', tradingpair, mode)
	graph = get_file_path('graph_gains', tradingpair, mode)
	with open(data_path, 'r') as f:
		gains_data = json.load(f)
		gains_data.pop('latest_weekly_UTS')
	listing_stats = pd.read_csv(stats_path, index_col= 0)
	successful_symbols = set(listing_stats[listing_stats.success].index)
	longest = 0
	plt.rcParams["figure.figsize"] = (20,10)
	ax = plt.gca()
	ax.set_ylim([0, 2000])
	week_of_double = {}
	for symbol in successful_symbols:
		weekly_gains = gains_data[symbol]
		no_of_weeks = list(range(len(weekly_gains)))
		if longest < len(weekly_gains):
			longest = len(weekly_gains)

		for week, gains in enumerate(weekly_gains):
			if gains >= 200:
				try:
					week_of_double[week] += 1
				except KeyError:
					week_of_double[week] = 1
				break
		# plt.plot(no_of_weeks, weekly_gains, label = symbol)
		# plt.legend(title="symbols", title_fontsize="large", loc='upper right', fontsize='xx-small', shadow=True, fancybox=True, bbox_to_anchor=(1.116, 1.2))
	plt.plot(list(range(longest)), [200]*longest, label = symbol, linestyle="--")
	plt.plot(list(range(longest)), [100]*longest, label = symbol, linestyle="--")
	for week, count in week_of_double.items():
		plt.plot([week, week], [100, 100*count], label = symbol, linestyle="--")
	plt.savefig(graph)


def graph2(tradingpair, mode="short_term"):

	stats_path = get_file_path('stats', tradingpair, mode)
	graph = get_file_path('graph_dates', tradingpair, mode)
	listing_stats = pd.read_csv(stats_path, index_col= 0)
	# filter out symbols without at least 26 weeks of data
	symbols_filtered = listing_stats.sort_values(by=['listing_date'])[(1642377600000 - listing_stats['listing_date']) / 604800000 >= 26]
	symbols_weeks_to_2x = symbols_filtered['week_of_2x'].to_dict()

	plt.rcParams["figure.figsize"] = (25,10)
	plt.bar(symbols_weeks_to_2x.keys(), symbols_weeks_to_2x.values(), color ='maroon', width = 0.6)
	prev = 0
	prev_quater = 6
	newyear = True
	for count, utx in enumerate(symbols_filtered['listing_date']):
		month = datetime.utcfromtimestamp((utx/1000)).month
		if month <= 3:
			if newyear:
				plt.plot([5, 5], [0, 26], linestyle="--")
				# plt.text(5, 15, datetime.utcfromtimestamp((utx/1000)).year)
				newyear = False
			plt.axvspan(0, 4, ymax=1, color ='yellow', alpha=0.1)
		elif month <= 6:
			if prev_quater <= 3:
				prev_quater = 6
				plt.axvspan(8, 16, ymax=1, color ='yellow', alpha=0.1)
			pass
		elif month <= 9:
			pass
		else:
			newyear = True
	plt.xticks(rotation=90)
	plt.xlabel('Symbols (release order)', weight='bold', size='large')
	plt.ylabel('Weeks to 2x', weight='bold', size='large')
	plt.title('Weeks to 2x against release time', weight='bold', size='large')
	
	plt.tight_layout()
	plt.savefig(graph)

if __name__ == "__main__":

	# symbols = get_USD_symbols("spot", tradingpair="USD")
	# scan_binance_listing_trends(symbols, "USD")
	# graph('USD')
	graph2('USD')
