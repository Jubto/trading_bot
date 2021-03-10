#!/bin/sh

self_dir=$(dirname "$(realpath -s "$0")")
cat "${self_dir}"/server_attributes/postfix_main_original.cf > /etc/postfix/main.cf # Revert postfix main.cf to original upon shutdown.
sed -i -re 's/^(Shutdown status:).*/\1 good/' "${self_dir}"/server_attributes/shutdown_status.txt # Set shutdown status to good.
