from decimal import Decimal
from wallet_manager import get_balance
from trade_log import log_trade, get_sol_usd_price
from jupiter_trader import fetch_jupiter_swap_route, execute_jupiter_swap
from auto_sell import mark_new_token
from risk_manager import is_risky_token
from utils import log
import config

MINT_SOL = "So11111111111111111111111111111111111111112"


async def execute_trade(trade):
    wallet = trade["wallet"]
    token_in = trade["token_in"]
    token_out = trade["token_out"]
    signature = trade["signature"]

    if is_risky_token(token_out):
        log(f"[RISK] Skipping risky token {token_out}")
        return

    balance = get_balance()
    if balance < config.MIN_BALANCE_SOL:
        log("Balance too low to trade.")
        return

    sol_amount = Decimal("0.01")  # Dynamically 1% of balance
    lamports = int(sol_amount * 1e9)

    if config.PRACTICE_MODE:
        log(f"[PRACTICE] Copying {wallet}: {token_out}")
        log_trade(token_out, "FAKECOIN", 0, sol_amount, f"sim-{signature[-6:]}")
        mark_new_token(token_out, get_sol_usd_price(), 0)
    else:
        route = fetch_jupiter_swap_route(token_in, token_out, lamports)
        if route:
            result = execute_jupiter_swap(route)
            if result:
                log(f"[LIVE] Executed buy: {result}")
                log_trade(token_out, "LIVECOIN", 0, sol_amount, result["result"])
                mark_new_token(token_out, get_sol_usd_price(), 0)
