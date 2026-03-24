import base64
import config

try:
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey
    from solana.rpc.api import Client
    def get_pubkey(kp): return kp.pubkey()
except ImportError:
    from solana.keypair import Keypair
    from solana.rpc.api import Client
    def get_pubkey(kp): return kp.public_key

client = Client(config.RPC_URL or config.HELIUS_RPC_URL)
wallet = Keypair.from_bytes(base64.b64decode(config.USER_WALLET_PRIVATE_KEY))

def get_balance() -> float:
    try:
        resp = client.get_balance(get_pubkey(wallet))
        # Handle both old dict response and new object response
        if hasattr(resp, 'value'):
            return resp.value / 1e9
        return resp["result"]["value"] / 1e9
    except Exception as e:
        from utils import log
        log(f"[WALLET] Balance fetch failed: {e}")
        return 0.0
