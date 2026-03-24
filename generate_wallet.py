"""
generate_wallet.py — generate a new Solana keypair for AlphaPulse.
 
Works with both old solana-py (solana.keypair) and new solders-based API.
"""
 
import base64
 
try:
    from solders.keypair import Keypair
except ImportError:
    from solana.keypair import Keypair
 
kp  = Keypair()
pub = str(kp.pubkey()) if hasattr(kp, "pubkey") else str(kp.public_key)
priv = base64.b64encode(bytes(kp)).decode()
 
print("=" * 60)
print("  NEW SOLANA WALLET GENERATED")
print("=" * 60)
print(f"  Public key  (wallet address) : {pub}")
print(f"  Private key (base64)         : {priv}")
print("=" * 60)
print("  IMPORTANT:")
print("  1. Save BOTH values somewhere safe offline")
print("  2. Add the private key to your .env as USER_WALLET_PRIVATE_KEY")
print("  3. Do NOT share or commit your private key")
print("  4. Do NOT fund this wallet with real money until bot is tested")
print("=" * 60)
 
