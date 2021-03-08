#!/bin/sh

# Exit 0 means continue python notify function
# Exit 1 means exit python notify function
# Exit 2 means re-run python notify function

if which postfix > /dev/null
then
    mkdir postfix_original 2>/dev/null
    cat /etc/postfix/main.cf > postfix_original/postfix_main_original.cf
    service postfix status > /dev/null
    if test $? -eq 0
        echo "Warning: A Postfix server instance is already running on this machince. Is it okay to restart the server?"
        echo -n 'Restart postfix server (y/n): '
        then while read response
        do 
            if test "$response" = 'y'
            then 
                service postfix stop >/dev/null
                break
            elif test "$response" = 'n'
            then   
                echo "Tradingbot server will not commence notification service. Run 'notify' command if you change your mind."
                exit 1
            else   
                echo "Invalid response, please enter either 'y' or 'n'"
                echo -n 'Restart postfix server (y/n): '  
            fi
        done < /dev/stdin
    elif test $? -eq 3
        then :
    fi
    sed -i -re 's/^smtp_tls_security_level.*//g' /etc/postfix/main.cf
    name=$(hostname -f)
    domain=$(hostname -f | sed -r 's/[^\.]*\.//')
    if grep -E "^myhostname =\s*${name}" /etc/postfix/main.cf
    then :
    else
        sed -i -re "s/^(myhostname =)*./\1 ${name}/" /etc/postfix/main.cf
    fi
    if grep -E "^mydestination = localhost\.${domain}"
        then :
    else
        sed -i -re "s/^(mydestination =).*/\1 localhost.${domain}, , localhost/" /etc/postfix/main.cf
    fi
    sed -i -re 's/(relayhost =).*/\1 [smtp.gmail.com]:587/' /etc/postfix/main.cf
    if test $(grep -E '###tradingbot modification applied###' /etc/postfix/main.cf | wc -l) -ge 2
    then :
    else
        cat >> /etc/postfix/main.cf << eof
        ###tradingbot modification applied###
        # Enables SASL authentication for postfix
        smtp_sasl_auth_enable = yes
        # Disallow methods that allow anonymous authentication
        smtp_sasl_security_options = noanonymous
        # Location of sasl_passwd we saved
        smtp_sasl_password_maps = hash:/etc/postfix/sasl/sasl_passwd_tradingbot
        # Enable STARTTLS encryption for SMTP
        smtp_tls_security_level = encrypt
        # Location of CA certificates for TLS
        smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt
        # TLS parameter
        smtpd_use_tls=yes
        ###tradingbot modification applied###
eof
    fi
    echo "Postfix configeration complete."
    if ls /etc/postfix/sasl | grep -E 'sasl_passwd_tradingbot.db'
    then
        gmail=$(grep -E '^notification gmail: ' server_attributes/postfix.txt | sed -r 's/^notification gmail: //')
        echo "Please ensure your gmail: ${gmail} has its 'Less secure app access' ON." # Note: Would normally use xdg-open, however this was built on WSL2 (could use wsl-open)
        echo "To check, follow the link: https://myaccount.google.com/lesssecureapps"
        echo "Starting postfix server ... "
        service postfix restart
        exit 0
    else
        echo "As this is the first time running the notification service of tradingbot, please perform the following instructions:"
        echo "First you must create a brand new gmail account to be used just for this service."
        echo "NOTE: The tradingbot server will require you to enter email and password once to store them. The password will be hashed."
        echo -n "Once you have created the account, hit enter: "
        read line
        echo "Enter full email address and assoicated password bellow:"
        while true
        do
            echo -n "Enter gmail address: "
            read email
            echo -n "Enter password: "
            read password1
            echo -n "Confirm password: "
            read password2
            if test "$password1" = "$password2"
            then
                echo "Tradingbot server will use gmail ${email} for notification communication, confirm? (y/n): "
                while read response
                do 
                    if test "$response" = 'y'
                    then
                        echo "[smtp.gmail.com]:587 ${email}:${password2}" | cat > /etc/postfix/sasl/sasl_passwd_tradingbot
                        postmap /etc/postfix/sasl/sasl_passwd_tradingbot
                        chown root:root /etc/postfix/sasl/sasl_passwd_tradingbot.db
                        chmod 600 /etc/postfix/sasl/sasl_passwd_tradingbot.db
                        rm /etc/postfix/sasl/sasl_passwd_tradingbot
                        mkdir server_attributes 2>/dev/null
                        echo "notification gmail: ${email}" | cat >> server_attributes/postfix.txt
                        echo "Password has been hashed."
                        echo "Postfix server will restart..."
                        service postfix restart
                        echo "To finalise setup, please set your 'Less secure app access' for the specified gmail to ON"
                        echo "Use this link to change it: https://myaccount.google.com/lesssecureapps" 
                        echo "Hit Enter once completed: "
                        read line
                        echo "Trading server and postfix server setup completed. Notifications service will now commence!"
                        exit 0
                    elif test "$response" = 'n'
                    then
                        echo "Server notification setup will not commence. To retry, run 'notify' command again."
                        exit 1 
                    else
                        echo "Invalid response, please enter either 'y' or 'n'"
                        echo "Tradingbot server will use gmail ${email} for notification communication, confirm? (y/n): "
                    fi
                done < /dev/stdin
            else
                echo "Passwords entered do not match. Please try again"
                continue
            fi
            break
        done
    fi
else
    echo 'Postfix SMTP is required for this program but is not on this system.'
    echo -n 'Install postfix (y/n): '
    while read response
    do 
        if test "$response" = 'y'
            then 
                echo "Installation process is about to commence."
                echo "NOTE: After installation, a postfix window will open. Hit enter for 'Internet Site'"
                echo "NOTE: Next, hit enter again when the next window opens (i.e. system mail name set to be deafult user domain name)"
                echo -n "Hit enter to commence installation:"
                read line
                apt-get install mailutils
                cat /etc/postfix/main.cf > postfix_original/postfix_main_original.cf
                exit 2 # for python
        elif test "$response" = 'n'
            then 
                echo "No postfix will be installed. Tradingbot notification service will not be activated."
                echo "Run notification command to try again if desired."
                exit 1 # for python
        else
            echo "Invalid response, please enter either 'y' or 'n'"
            echo -n 'Install postfix (y/n): '
            continue
        fi
        break
    done < /dev/stdin
fi
