from solana.keypair import Keypair
import base64

wallet = Keypair.generate()
private_key_b64 = base64.b64encode(wallet.secret_key).decode("utf-8")

print("✅ Your new wallet address:\n", wallet.public_key)
print("\n🔐 Paste this into config.py as USER_WALLET_PRIVATE_KEY:")
print(private_key_b64)
