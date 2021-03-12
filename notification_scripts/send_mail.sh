#!/bin/sh

# Takes in arguments - any number of coin data files (i.e. 1 json/csv summary of each coin) - each file will contain their score on the header which this script
# will extract (using a for looping over the files) 

# email subjects should have date to make them uniqe + coin + mode (either signal or update)

# Two modes, signal mode and update mode
# signal mode (1) is when the notification server detects a bullish signal score and sends a mode1 email
# Update mode (2) is when the user has set the notification server to email periodically with an overview/update of all coins they're monitoring
# {'user':'jubjubfriend@gmail.com', 'mode':'1', 'score':'1', 'details':'0', 'files':'file1,file2'}
# $1 mode type
# $2 score
# $3 General stats (%gain, amount holding, total amount value)
# $3+ files (csv and graphs)
mode="$1"
score="$2"
echo "arguments are: $@"
files=$(echo "$@" | cut -d' ' -f4-)
# attchments
# # email=

# for file in $files
# do 
#     attchments="${attchments}-A ${file} "
# done

# echo "anything" | mail -s "tradingbot script3" -A "$file" email@gmail.com
