from solana.keypair import Keypair
import base64
import logging
from utils import log

wallet = Keypair.generate()
private_key_b64 = base64.b64encode(wallet.secret_key).decode("utf-8")

log("✅ Your new wallet address:\n" + str(wallet.public_key), logging.INFO)
log("\n🔐 Paste this into config.py as USER_WALLET_PRIVATE_KEY:", logging.INFO)
log(private_key_b64, logging.INFO)
