from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware  # Necessary for POA chains
from datetime import datetime
import json
import os
from eth_account import Account


def connect_to(chain):
    if chain == 'source':
        api_url = "https://api.avax-test.network/ext/bc/C/rpc"  # Avalanche Testnet
    elif chain == 'destination':
        api_url = "https://data-seed-prebsc-1-s1.binance.org:8545/"  # BNB Testnet
    else:
        raise ValueError("Invalid chain")

    w3 = Web3(Web3.HTTPProvider(api_url))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_contract_info(chain, contract_info):
    try:
        with open(contract_info, 'r') as f:
            contracts = json.load(f)
    except Exception as e:
        print(f"Failed to read contract info\nPlease contact your instructor\n{e}")
        return 0
    return contracts


def scan_blocks(chain, contract_info="contract_info.json"):
    """
        chain - (string) should be either "source" or "destination"
        Scan the last 5 blocks of the source and destination chains
        Look for 'Deposit' events on the source chain and 'Unwrap' events on the destination chain
        When Deposit events are found on the source chain, call the 'wrap' function the destination chain
        When Unwrap events are found on the destination chain, call the 'withdraw' function on the source chain
    """

    # This is different from Bridge IV where chain was "avax" or "bsc"
    if chain not in ['source','destination']:
        print( f"Invalid chain: {chain}" )
        return 0
    
    # YOUR CODE HERE
    # 1. Setup: Load warden key, connect to chains, and instantiate contracts
    private_key = os.environ.get('PRIVATE_KEY')
    if not private_key:
        print("Error: PRIVATE_KEY environment variable not set.")
        return 0

    w3_source = connect_to('source')
    w3_dest = connect_to('destination')

    warden_account = w3_source.eth.account.from_key(private_key)
    warden_address = warden_account.address

    source_info = get_contract_info('source', contract_info)
    dest_info = get_contract_info('destination', contract_info)

    source_contract = w3_source.eth.contract(address=source_info['address'], abi=source_info['abi'])
    dest_contract = w3_dest.eth.contract(address=dest_info['address'], abi=dest_info['abi'])

    # 2. Logic to listen on the source chain for 'Deposit' events
    if chain == 'source':
        w3_listen = w3_source
        contract_listen = source_contract
        event_name = 'Deposit'

        latest_block = w3_listen.eth.block_number
        from_block = max(0, latest_block - 4)  # Scan last 5 blocks

        event_filter = contract_listen.events[event_name].create_filter(
            fromBlock=from_block,
            toBlock='latest'
        )
        events = event_filter.get_all_entries()

        for event in events:
            print(f"Found Deposit event on source chain: {event['args']}")
            args = event['args']
            
            # Prepare and send 'wrap' transaction to the destination chain
            try:
                nonce = w3_dest.eth.get_transaction_count(warden_address)
                tx_params = {
                    'from': warden_address,
                    'nonce': nonce,
                    'gas': 300000,
                    'gasPrice': w3_dest.eth.gas_price,
                    'chainId': w3_dest.eth.chain_id,
                }
                
                wrap_tx = dest_contract.functions.wrap(
                    args['token'],
                    args['recipient'],
                    args['amount']
                ).build_transaction(tx_params)

                signed_tx = w3_dest.eth.account.sign_transaction(wrap_tx, private_key)
                tx_hash = w3_dest.eth.send_raw_transaction(signed_tx.rawTransaction)
                print(f"Sent 'wrap' transaction to destination chain. Hash: {w3_dest.to_hex(tx_hash)}")

            except Exception as e:
                print(f"Failed to send 'wrap' transaction: {e}")

    # 3. Logic to listen on the destination chain for 'Unwrap' events
    elif chain == 'destination':
        w3_listen = w3_dest
        contract_listen = dest_contract
        event_name = 'Unwrap'

        latest_block = w3_listen.eth.block_number
        from_block = max(0, latest_block - 4)  # Scan last 5 blocks

        event_filter = contract_listen.events[event_name].create_filter(
            fromBlock=from_block,
            toBlock='latest'
        )
        events = event_filter.get_all_entries()

        for event in events:
            print(f"Found Unwrap event on destination chain: {event['args']}")
            args = event['args']
            
            # Prepare and send 'withdraw' transaction to the source chain
            try:
                nonce = w3_source.eth.get_transaction_count(warden_address)
                tx_params = {
                    'from': warden_address,
                    'nonce': nonce,
                    'gas': 300000,
                    'gasPrice': w3_source.eth.gas_price,
                    'chainId': w3_source.eth.chain_id,
                }

                withdraw_tx = source_contract.functions.withdraw(
                    args['underlying_token'],
                    args['to'],  # The recipient of the withdrawal
                    args['amount']
                ).build_transaction(tx_params)

                signed_tx = w3_source.eth.account.sign_transaction(withdraw_tx, private_key)
                tx_hash = w3_source.eth.send_raw_transaction(signed_tx.rawTransaction)
                print(f"Sent 'withdraw' transaction to source chain. Hash: {w3_source.to_hex(tx_hash)}")
            
            except Exception as e:
                print(f"Failed to send 'withdraw' transaction: {e}")
