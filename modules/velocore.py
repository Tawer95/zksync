import random
import time
from typing import Union

from loguru import logger
from web3 import Web3
from config import VELOCORE_ROUTER_ABI, VELOCORE_CONTRACTS, ZKSYNC_TOKENS
from .account import Account


class Velocore(Account):
    def __init__(self, account_id: int, private_key: str, proxy: Union[None, str]) -> None:
        super().__init__(account_id=account_id, private_key=private_key, proxy=proxy, chain="zksync")

        self.swap_contract = self.get_contract(VELOCORE_CONTRACTS["router"], VELOCORE_ROUTER_ABI)
        self.tx = {
            "from": self.address,
            "gas": random.randint(2900000, 3100000),
            "gasPrice": self.w3.eth.gas_price,
            "nonce": self.w3.eth.get_transaction_count(self.address)
        }

    def get_min_amount_out(self, from_token: str, to_token: str, amount: int, slippage: float):
        min_amount_out = self.swap_contract.functions.getAmountOut(
            amount,
            Web3.to_checksum_address(from_token),
            Web3.to_checksum_address(to_token)
        ).call()
        return int(min_amount_out[0] - (min_amount_out[0] / 100 * slippage))

    def swap_to_token(self, from_token: str, to_token: str, amount: int, slippage: int):
        self.tx.update({"value": amount})

        deadline = int(time.time()) + 1000000

        min_amount_out = self.get_min_amount_out(ZKSYNC_TOKENS[from_token], ZKSYNC_TOKENS[to_token], amount, slippage)

        contract_txn = self.swap_contract.functions.swapExactETHForTokens(
            min_amount_out,
            [
                [
                    Web3.to_checksum_address(ZKSYNC_TOKENS[from_token]),
                    Web3.to_checksum_address(ZKSYNC_TOKENS[to_token]),
                    False
                ]
            ],
            self.address,
            deadline
        ).build_transaction(self.tx)

        return contract_txn

    def swap_to_eth(self, from_token: str, to_token: str, amount: int, slippage: int):
        token_address = Web3.to_checksum_address(ZKSYNC_TOKENS[from_token])

        self.approve(amount, token_address, Web3.to_checksum_address(VELOCORE_CONTRACTS["router"]))
        self.tx.update({"nonce": self.w3.eth.get_transaction_count(self.address)})

        deadline = int(time.time()) + 1000000

        min_amount_out = self.get_min_amount_out(ZKSYNC_TOKENS[from_token], ZKSYNC_TOKENS[to_token], amount, slippage)

        contract_txn = self.swap_contract.functions.swapExactTokensForETH(
            amount,
            min_amount_out,
            [
                [
                    Web3.to_checksum_address(ZKSYNC_TOKENS[from_token]),
                    Web3.to_checksum_address(ZKSYNC_TOKENS[to_token]),
                    False
                ]
            ],
            self.address,
            deadline
        ).build_transaction(self.tx)

        return contract_txn

    def swap(
            self,
            from_token: str,
            to_token: str,
            min_amount: float,
            max_amount: float,
            decimal: int,
            slippage: int,
            all_amount: bool
    ):
        amount_wei, amount, balance = self.get_amount(from_token, min_amount, max_amount, decimal, all_amount)

        logger.info(
            f"[{self.account_id}][{self.address}] Swap on Velocore – {from_token} -> {to_token} | {amount} {from_token}"
        )

        try:
            if from_token == "ETH":
                contract_txn = self.swap_to_token(from_token, to_token, amount_wei, slippage)
            else:
                contract_txn = self.swap_to_eth(from_token, to_token, amount_wei, slippage)

            signed_txn = self.sign(contract_txn)

            txn_hash = self.send_raw_transaction(signed_txn)

            self.wait_until_tx_finished(txn_hash.hex())
        except Exception as e:
            logger.error(f"[{self.account_id}][{self.address}] Error | {e}")
