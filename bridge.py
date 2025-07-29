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


def get_warden_key(contract_info_path="contract_info.json"):
    """Retrieve the warden's private key from the contract info JSON file."""
    try:
        with open(contract_info_path) as contract_file:
            config = json.load(contract_file)
        key = config.get("warden_key")
        if key is None:
            print("Warden key not found in contract info.")
        return key
    except (FileNotFoundError, json.JSONDecodeError) as error:
        print(f"Unable to extract warden key: {error}")
        return None

def scan_blocks(chain, contract_info_path="contract_info.json"):
    """Scan recent blocks for bridge events"""
    if chain not in ['source', 'destination']:
        print(f"Invalid chain: {chain}")
        return 0

    try:
        web3 = connect_to(chain)
        config = get_contract_info(chain, contract_info_path)
        if not config:
            return 0

        contract = web3.eth.contract(
            address=Web3.to_checksum_address(config['address']),
            abi=config['abi']
        )

        latest = web3.eth.block_number
        start_block = max(0, latest - 50)

        print(f"Checking blocks {start_block} to {latest} on '{chain}'")

        if chain == 'source':
            deposit_logs = contract.events.Deposit.create_filter(
                from_block=start_block, to_block=latest
            ).get_all_entries()

            for log in deposit_logs:
                print(f"[{datetime.utcnow()}] Deposit event: {log}")
                handle_deposit_event(log, contract_info_path)

        elif chain == 'destination':
            unwrap_logs = contract.events.Unwrap.create_filter(
                from_block=start_block, to_block=latest
            ).get_all_entries()

            print(f"Found {len(unwrap_logs)} Unwrap events")

            for log in unwrap_logs:
                print(f"Unwrap event: {log}")
                handle_unwrap_event(log, contract_info_path)

    except Exception as err:
        print(f"Error while scanning chain '{chain}': {err}")
        return 0

    return 1


def handle_deposit_event(event, contract_info_path="contract_info.json"):
    """Trigger wrap() on the destination chain after Deposit event."""
    print(f"Initiating wrap() for deposit")

    try:
        details = event['args']
        token_addr = Web3.to_checksum_address(details['token'])
        recipient_addr = Web3.to_checksum_address(details['recipient'])
        amount = details['amount']

        dest_web3 = connect_to('destination')
        dest_info = get_contract_info('destination', contract_info_path)
        if not dest_info:
            print("Destination contract details missing.")
            return

        dest_contract = dest_web3.eth.contract(
            address=Web3.to_checksum_address(dest_info['address']),
            abi=dest_info['abi']
        )

        key = get_warden_key(contract_info_path)
        if not key:
            print("Missing warden private key.")
            return
        if not key.startswith('0x'):
            key = '0x' + key

        account = dest_web3.eth.account.from_key(key)

        tx = dest_contract.functions.wrap(token_addr, recipient_addr, amount)
        gas = tx.estimate_gas({'from': account.address})

        tx_data = tx.build_transaction({
            'from': account.address,
            'nonce': dest_web3.eth.get_transaction_count(account.address, 'pending'),
            'gas': gas + 10000,
            'gasPrice': dest_web3.eth.gas_price
        })

        signed = dest_web3.eth.account.sign_transaction(tx_data, key)
        tx_hash = dest_web3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = dest_web3.eth.wait_for_transaction_receipt(tx_hash)

        print(f" wrap() confirmed: {receipt['transactionHash'].hex()}")

    except Exception as e:
        print(f" wrap() failed: {e}")


def handle_unwrap_event(event, contract_info_path="contract_info.json"):
    """Trigger withdraw() on the source chain after Unwrap event."""
    print(f"Initiating withdraw() for unwrap")

    try:
        details = event['args']
        base_token = Web3.to_checksum_address(details['underlying_token'])
        recipient_addr = Web3.to_checksum_address(details['to'])
        amount = details['amount']

        source_web3 = connect_to('source')
        source_info = get_contract_info('source', contract_info_path)
        if not source_info:
            print("Source contract details missing.")
            return

        source_contract = source_web3.eth.contract(
            address=Web3.to_checksum_address(source_info['address']),
            abi=source_info['abi']
        )

        key = get_warden_key(contract_info_path)
        if not key:
            print("Missing warden private key.")
            return
        if not key.startswith('0x'):
            key = '0x' + key

        account = source_web3.eth.account.from_key(key)

        tx = source_contract.functions.withdraw(base_token, recipient_addr, amount)
        gas = tx.estimate_gas({'from': account.address})

        tx_data = tx.build_transaction({
            'from': account.address,
            'nonce': source_web3.eth.get_transaction_count(account.address, 'pending'),
            'gas': gas + 10000,
            'gasPrice': source_web3.eth.gas_price
        })

        signed = source_web3.eth.account.sign_transaction(tx_data, key)
        tx_hash = source_web3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = source_web3.eth.wait_for_transaction_receipt(tx_hash)

        print(f"withdraw() confirmed: {receipt['transactionHash'].hex()}")

    except Exception as e:
        print(f"withdraw() failed: {e}")


if __name__ == "__main__":
    print(f"Running cross-chain bridge relayer")
    scan_blocks('source')
    scan_blocks('destination')