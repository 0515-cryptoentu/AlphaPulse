from solana.keypair import Keypair
from solana.rpc.api import Client
import base64
import config

# Ensure mandatory configuration is available before attempting to create the
# client or wallet objects.  ``config`` will have already validated that
# ``RPC_URL`` and ``USER_WALLET_PRIVATE_KEY`` are present, but we keep these
# explicit checks here for clarity when this module is used standalone.
if not config.RPC_URL:
    raise EnvironmentError("RPC_URL environment variable is not set")
if not config.USER_WALLET_PRIVATE_KEY:
    raise EnvironmentError("USER_WALLET_PRIVATE_KEY environment variable is not set")

client = Client(config.RPC_URL)
wallet = Keypair.from_secret_key(base64.b64decode(config.USER_WALLET_PRIVATE_KEY))


def get_balance():
    return client.get_balance(wallet.public_key)["result"]["value"] / 1e9
