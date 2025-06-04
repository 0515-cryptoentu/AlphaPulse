from solana.keypair import Keypair
from solana.rpc.api import Client
import base64
import config

# ``config`` now centrally validates environment variables so we no longer
# perform local checks here.

client = Client(config.RPC_URL)
wallet = Keypair.from_secret_key(base64.b64decode(config.USER_WALLET_PRIVATE_KEY))


def get_balance():
    return client.get_balance(wallet.public_key)["result"]["value"] / 1e9
