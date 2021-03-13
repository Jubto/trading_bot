#!/bin/sh

# Script accepts the following parameters: {'user':email, 'title':subject, 'details':details, 'files':files}

email="$1"
title="$2 "$(date | cut -d' ' -f1-3)""
body=$(echo "$3" | tr '#' '\n')
attachments=$(echo "$4" | tr ',' ' ')

for attachment in $attachments
do 
    files="${files}-A ${attachment} "
done

echo "$body" | mail -s "$title" $files "$email"

# echo $email
# echo $title
# echo $body
# echo $files
