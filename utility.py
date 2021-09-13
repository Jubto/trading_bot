from enums import SYMBOLS_URL1, SYMBOLS_URL2, SYMBOLS_URL3

def get_url(mode):
	if mode == "spot":
		return SYMBOLS_URL1
	elif mode == "um":
		return SYMBOLS_URL2
	elif mode == "cm":
		return SYMBOLS_URL3


def loading_bar():
	# Use this functions throughout the processes that take noticeable time in server/get_candles
	pass