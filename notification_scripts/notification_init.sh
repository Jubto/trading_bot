#!/bin/sh

# Exit 0 means continue python notify function
# Exit 1 means exit python notify function

self_dir=$(dirname "$0") # This will always be an absolute path because these scripts are run from notification_server.py 

if grep -E -q 'Shutdown status: good' "${self_dir}"/server_attributes/shutdown_status.txt 
then 
    exit 0
elif grep -E -q '###tradingbot modification applied###' /etc/postfix/main.cf
    then
        echo "WARNING: Tradingbot server did not shutdown safely using 'quit' command."
        echo "This has resulted in /etc/postfix/main.cf retaining the tradingbot server settings without getting reverted to it's prior settings."
        echo "The tradingbot server always makes a copy of main.cf before it modifies it,"
        echo "however it cannot guarentee this is the most recent version of main.cf on your system due to the invalid shutdown."
        echo "This is an issue because tradingbot server always sets the main.cf back to its stored back up version upon shutdown."
        echo -n "Press enter to view tradingbot servers backup of /etc/postfix/main.cf:"
        read line
        cat "${self_dir}"/server_attributes/postfix_main_original.cf
        echo -n "\nIs this backup of main.cf fine for tradingbot server to set as your system main.cf after shutdown? (y/n):"
        while read response
        do
            case "$response" in
            [Yy]|[Yy]es )
                            cat "${self_dir}"/server_attributes/postfix_main_original.cf > /etc/postfix/main.cf
                            echo "/etc/postfix/main.cf has been reverted to last back up version."
                            echo "Server process will continue as normal."
                            exit 0 ;;
            [Nn]|[Nn]o  )
                            echo "Server will not revert /etc/postfix/main.cf to the stored back up version."
                            break ;;
            *|""        )
                            echo "Invalid response, please enter either 'y' or 'n'"
                            echo -n 'Set tradingbot server back of /etc/postfix/main.cf as your system deafult? (y/n): '
            esac
        done < /dev/stdin
        echo -n "Would you like to enter an alternative version of main.cf to set as deafult? (y/n)"
        while read response
        do
            case "$response" in
            [Yy]|[Yy]es )
                            echo -n "Provide file path to alternative version of main.cf:"
                            read path
                            if ls -- "$path" >/dev/null 2>&1
                            then 
                                cat "$path" > "${self_dir}"/server_attributes/postfix_main_original.cf
                                echo "Server process will continue as normal."
                                exit 0
                            else
                                echo "Invalid path, file does not exist. Please try again:" 
                                echo -n "Would you like to enter an alternative version of main.cf to set as deafult? (y/n)"
                                continue
                            fi ;;
            [Nn]|[Nn]o  )
                            exit 1 ;;
            *|""        )
                            echo "Invalid response, please enter either 'y' or 'n'"
                            echo -n "Would you like to enter an alternative version of main.cf to set as deafult? (y/n)"
                            continue
            esac
        done < /dev/stdin
fi
