from solana.keypair import Keypair
from solana.rpc.api import Client
from solana.transaction import Transaction
import base64
import config

client = Client(config.RPC_URL)
wallet = Keypair.from_secret_key(base64.b64decode(config.USER_WALLET_PRIVATE_KEY))


def get_balance():
    return client.get_balance(wallet.public_key)["result"]["value"] / 1e9
