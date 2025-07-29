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
    """Get the warden's private key from contract info"""
    try:
        with open(contract_info_path, 'r') as f:
            data = json.load(f)
        return data['warden_key']
    except Exception as e:
        print(f"Failed to read warden key: {e}")
        return None

def scan_blocks(chain, contract_info_path="contract_info.json"):
    """Scan recent blocks for bridge events"""
    if chain not in ['source', 'destination']:
        print(f"Invalid chain: {chain}")
        return 0

    try:
        w3 = connect_to(chain)
        contract_data = get_contract_info(chain, contract_info_path)
        if not contract_data:
            return 0

        contract_address = Web3.to_checksum_address(contract_data['address'])
        contract_abi = contract_data['abi']
        contract = w3.eth.contract(address=contract_address, abi=contract_abi)
        
        current_block = w3.eth.block_number
        from_block = max(0, current_block - 50)  # Scan more blocks to catch events

        print(f"[{datetime.utcnow()}] Scanning blocks {from_block} to {current_block} on {chain} chain")

        if chain == 'source':
            # Look for Deposit events on source chain
            events = contract.events.Deposit.create_filter(
                from_block=from_block, 
                to_block=current_block
            ).get_all_entries()
            
            for event in events:
                print(f"[{datetime.utcnow()}] Found Deposit event: {event}")
                handle_deposit_event(event, contract_info_path)
                
        elif chain == 'destination':
            # Look for Unwrap events on destination chain
            events = contract.events.Unwrap.create_filter(
                from_block=from_block, 
                to_block=current_block
            ).get_all_entries()
            
            print(f"[{datetime.utcnow()}] Found {len(events)} Unwrap events")
            
            for event in events:
                print(f"[{datetime.utcnow()}] Found Unwrap event: {event}")
                handle_unwrap_event(event, contract_info_path)

    except Exception as e:
        print(f"Error scanning blocks on {chain}: {e}")
        return 0

    return 1

def handle_deposit_event(deposit_event, contract_info_path="contract_info.json"):
    """Handle Deposit event by calling wrap() on destination chain"""
    print(f"[{datetime.utcnow()}] Handling Deposit event - calling wrap() on destination chain")

    # Extract event arguments
    args = deposit_event['args']
    token = Web3.to_checksum_address(args['token'])
    recipient = Web3.to_checksum_address(args['recipient'])
    amount = args['amount']

    # Connect to destination chain
    dest_w3 = connect_to('destination')
    dest_contract_data = get_contract_info('destination', contract_info_path)
    if not dest_contract_data:
        print("Failed to get destination contract data")
        return

    dest_contract_address = Web3.to_checksum_address(dest_contract_data['address'])
    dest_contract_abi = dest_contract_data['abi']
    dest_contract = dest_w3.eth.contract(address=dest_contract_address, abi=dest_contract_abi)
    
    # Get warden key and create account
    warden_key = get_warden_key(contract_info_path)
    if not warden_key:
        print("Failed to get warden key")
        return
        
    # Ensure key has 0x prefix
    if not warden_key.startswith('0x'):
        warden_key = '0x' + warden_key
        
    warden_account = dest_w3.eth.account.from_key(warden_key)

    try:
        # Estimate gas and build transaction
        gas_estimate = dest_contract.functions.wrap(token, recipient, amount).estimate_gas({
            'from': warden_account.address
        })
        
        tx = dest_contract.functions.wrap(token, recipient, amount).build_transaction({
            'from': warden_account.address,
            'nonce': dest_w3.eth.get_transaction_count(warden_account.address, 'pending'),
            'gas': gas_estimate + 10000,  # Add buffer for gas
            'gasPrice': dest_w3.eth.gas_price
        })
        
        # Sign and send transaction
        signed = dest_w3.eth.account.sign_transaction(tx, warden_key)
        tx_hash = dest_w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = dest_w3.eth.wait_for_transaction_receipt(tx_hash)
        
        print(f"[{datetime.utcnow()}] Wrap transaction confirmed: {receipt['transactionHash'].hex()}")
        
    except Exception as e:
        print(f"Error in wrap transaction: {e}")

def handle_unwrap_event(unwrap_event, contract_info_path="contract_info.json"):
    """Handle Unwrap event by calling withdraw() on source chain"""
    print(f"[{datetime.utcnow()}] Handling Unwrap event - calling withdraw() on source chain")

    # Extract event arguments
    args = unwrap_event['args']
    underlying_token = Web3.to_checksum_address(args['underlying_token'])
    recipient = Web3.to_checksum_address(args['to'])
    amount = args['amount']

    # Connect to source chain
    source_w3 = connect_to('source')
    source_contract_data = get_contract_info('source', contract_info_path)
    if not source_contract_data:
        print("Failed to get source contract data")
        return

    source_contract_address = Web3.to_checksum_address(source_contract_data['address'])
    source_contract_abi = source_contract_data['abi']
    source_contract = source_w3.eth.contract(address=source_contract_address, abi=source_contract_abi)
    
    # Get warden key and create account
    warden_key = get_warden_key(contract_info_path)
    if not warden_key:
        print("Failed to get warden key")
        return
        
    # Ensure key has 0x prefix
    if not warden_key.startswith('0x'):
        warden_key = '0x' + warden_key
        
    warden_account = source_w3.eth.account.from_key(warden_key)

    try:
        # Estimate gas and build transaction
        gas_estimate = source_contract.functions.withdraw(underlying_token, recipient, amount).estimate_gas({
            'from': warden_account.address
        })
        
        tx = source_contract.functions.withdraw(underlying_token, recipient, amount).build_transaction({
            'from': warden_account.address,
            'nonce': source_w3.eth.get_transaction_count(warden_account.address, 'pending'),
            'gas': gas_estimate + 10000,  # Add buffer for gas
            'gasPrice': source_w3.eth.gas_price
        })
        
        # Sign and send transaction
        signed = source_w3.eth.account.sign_transaction(tx, warden_key)
        tx_hash = source_w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = source_w3.eth.wait_for_transaction_receipt(tx_hash)
        
        print(f"[{datetime.utcnow()}] Withdraw transaction confirmed: {receipt['transactionHash'].hex()}")
        
    except Exception as e:
        print(f"Error in withdraw transaction: {e}")

if __name__ == "__main__":
    print(f"[{datetime.utcnow()}] Starting bridge script...")
    scan_blocks('source')
    scan_blocks('destination')