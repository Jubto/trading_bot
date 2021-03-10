#!/bin/sh

# Takes in arguments - any number of coin data files (i.e. 1 json/csv summary of each coin) - each file will contain their score on the header which this script
# will extract (using a for looping over the files) 

# Two modes, signal mode and update mode
# signal mode (1) is when the notification server detects a bullish signal score and sends a mode1 email
# Update mode (2) is when the user has set the notification server to email periodically with an overview/update of all coins they're monitoring
# $1 mode type
# $2 score
# $3+ files (csv and graphs)
args=$(echo "$@" | cut -d' ' -f3-)

for file in $args
do echo $file
done

# echo "anything" | mail -s "tradingbot script3" -A "$file" email@gmail.com
