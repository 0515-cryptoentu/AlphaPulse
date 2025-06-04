#!/bin/sh
# Encrypt a wallet private key when Vault is unavailable.
# Usage: encrypt_wallet_key.sh <base64-key> <output-file>

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <base64-key> <output-file>" >&2
    exit 1
fi

# shellcheck disable=SC2002
echo "$1" | openssl aes-256-cbc -salt -out "$2"
echo "Encrypted key saved to $2"
