from enums import SYMBOLS_URL1, SYMBOLS_URL2, SYMBOLS_URL3, DEFAULT_SCORING_TIMEFRAMES

def get_url(mode):
	if mode == "spot":
		return SYMBOLS_URL1
	elif mode == "um":
		return SYMBOLS_URL2
	elif mode == "cm":
		return SYMBOLS_URL3

def filter_market_periods(market_periods, start_uts, final_uts):
    filtered_market_period = []
    for market_period in market_periods:
        market_period_start, market_period_end = market_period
        if (market_period_start - final_uts).days > 0:
            continue # bear market out of range
        if (start_uts - market_period_end).days > 0:
            continue # bear market out of range
        if (start_uts - market_period_start).days > 0:
            market_period_start = start_uts
        if (market_period_end - final_uts).days > 0:
            market_period_end = final_uts
        filtered_market_period.append([market_period_start, market_period_end])
    return filtered_market_period


def get_filename_extension(custom_timeframes=[]):
    return '-'.join(custom_timeframes) if custom_timeframes else '-'.join(DEFAULT_SCORING_TIMEFRAMES)


def loading_bar():
	# Use this functions throughout the processes that take noticeable time in server/get_candles
	pass