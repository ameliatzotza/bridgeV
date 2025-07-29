from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware #Necessary for POA chains
from datetime import datetime
import json
import pandas as pd
import os
from eth_account import Account


def connect_to(chain):
    if chain == 'source':  # The source contract chain is avax
        api_url = f"https://api.avax-test.network/ext/bc/C/rpc" #AVAX C-chain testnet

    if chain == 'destination':  # The destination contract chain is bsc
        api_url = f"https://data-seed-prebsc-1-s1.binance.org:8545/" #BSC testnet

    if chain in ['source','destination']:
        w3 = Web3(Web3.HTTPProvider(api_url))
        # inject the poa compatibility middleware to the innermost layer
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_contract_info(chain, contract_info):
    """
        Load the contract_info file into a dictionary
        This function is used by the autograder and will likely be useful to you
    """
    try:
        with open(contract_info, 'r')  as f:
            contracts = json.load(f)
    except Exception as e:
        print( f"Failed to read contract info\nPlease contact your instructor\n{e}" )
        return 0
    return contracts[chain]



def scan_blocks(chain, contract_info="contract_info.json"):
    if chain not in ['source', 'destination']:
        print(f"Invalid chain: {chain}")
        return 0

    # Load contract info
    contracts = get_contract_info(chain, contract_info)
    contract_address = contracts["address"]
    abi = contracts["abi"]

    w3 = connect_to(chain)
    contract = w3.eth.contract(address=contract_address, abi=abi)

    warden_key = os.getenv("WARDEN_PRIVATE_KEY")
    if not warden_key:
        print("WARDEN_PRIVATE_KEY not found in environment variables.")
        return

    warden = Account.from_key(warden_key)

    other_chain = 'destination' if chain == 'source' else 'source'
    other_contracts = get_contract_info(other_chain, contract_info)
    other_w3 = connect_to(other_chain)
    other_contract = other_w3.eth.contract(address=other_contracts["address"], abi=other_contracts["abi"])

    latest_block = w3.eth.block_number
    from_block = max(0, latest_block - 5)
    to_block = latest_block

    try:
        if chain == 'source':
            # Low-level filter for Deposit events
            deposit_event_signature = w3.keccak(text="Deposit(address,address,uint256)").hex()
            logs = w3.eth.get_logs({
                "fromBlock": from_block,
                "toBlock": to_block,
                "address": contract_address,
                "topics": [deposit_event_signature]
            })

            for log in logs:
                event = contract.events.Deposit().processLog(log)
                args = event["args"]
                token = args["token"]
                to = args["recipient"]
                amount = args["amount"]

                tx = other_contract.functions.wrap(token, to, amount).build_transaction({
                    "from": warden.address,
                    "nonce": other_w3.eth.get_transaction_count(warden.address),
                    "gas": 500000,
                    "gasPrice": other_w3.eth.gas_price,
                    "chainId": other_w3.eth.chain_id
                })
                signed_tx = warden.sign_transaction(tx)
                tx_hash = other_w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                print(f"✅ wrap() called: {tx_hash.hex()}")

        elif chain == 'destination':
            # Low-level filter for Unwrap events
            unwrap_event_signature = w3.keccak(text="Unwrap(address,address,uint256)").hex()
            logs = w3.eth.get_logs({
                "fromBlock": from_block,
                "toBlock": to_block,
                "address": contract_address,
                "topics": [unwrap_event_signature]
            })

            for log in logs:
                event = contract.events.Unwrap().processLog(log)
                args = event["args"]
                token = args["underlying_token"]
                to = args["to"]
                amount = args["amount"]

                tx = other_contract.functions.withdraw(token, to, amount).build_transaction({
                    "from": warden.address,
                    "nonce": other_w3.eth.get_transaction_count(warden.address),
                    "gas": 500000,
                    "gasPrice": other_w3.eth.gas_price,
                    "chainId": other_w3.eth.chain_id
                })
                signed_tx = warden.sign_transaction(tx)
                tx_hash = other_w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                print(f"✅ withdraw() called: {tx_hash.hex()}")

    except Exception as e:
        print(f"⚠️ Error scanning blocks: {e}")

if __name__ == "__main__":
    scan_blocks("source")
    scan_blocks("destination")
