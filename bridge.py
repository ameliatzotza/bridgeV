from web3 import Web3
from datetime import datetime
import json

def connect_to(chain):
    """Connect to the appropriate blockchain network"""
    if chain == 'source':
        # Avalanche Testnet (Fuji)
        api_url = "https://api.avax-test.network/ext/bc/C/rpc"
    elif chain == 'destination':
        # BSC Testnet
        api_url = "https://data-seed-prebsc-1-s1.binance.org:8545/"
    else:
        raise ValueError("Invalid chain name")
    
    w3 = Web3(Web3.HTTPProvider(api_url))
    

    
    return w3

def get_contract_info(chain, contract_info_path="contract_info.json"):
    """Load contract information from JSON file"""
    try:
        with open(contract_info_path, 'r') as f:
            contracts = json.load(f)
        return contracts[chain]
    except Exception as e:
        print(f"Failed to read contract info: {e}")
        return None

def get_warden_key(contract_info_path="contract_info.json"):
    """Retrieve the warden's private key from the contract info file."""
    try:
        with open(contract_info_path, "r") as file:
            return json.load(file).get("warden_key")
    except (OSError, json.JSONDecodeError, KeyError) as err:
        print(f"Error retrieving warden key: {err}")
        return None

def scan_blocks(chain, contract_info_path="contract_info.json"):
    """Scan recent blocks for relevant events on the specified chain."""
    if chain not in ("source", "destination"):
        print(f"Invalid chain specified: {chain}")
        return 0

    try:
        w3 = connect_to(chain)
        contract_data = get_contract_info(chain, contract_info_path)
        if not contract_data:
            return 0

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_data["address"]),
            abi=contract_data["abi"]
        )

        latest_block = w3.eth.block_number
        from_block = max(0, latest_block - 50)

        print(f"[{datetime.utcnow()}] Scanning blocks {from_block} to {latest_block} on {chain}")

        if chain == "source":
            events = contract.events.Deposit.create_filter(
                from_block=from_block, to_block=latest_block
            ).get_all_entries()

            for event in events:
                print(f"[{datetime.utcnow()}] Detected Deposit event: {event}")
                handle_deposit_event(event, contract_info_path)

        elif chain == "destination":
            events = contract.events.Unwrap.create_filter(
                from_block=from_block, to_block=latest_block
            ).get_all_entries()

            print(f"[{datetime.utcnow()}] Detected {len(events)} Unwrap events")
            for event in events:
                print(f"[{datetime.utcnow()}] Unwrap event: {event}")
                handle_unwrap_event(event, contract_info_path)

    except Exception as err:
        print(f"Error scanning blocks on {chain} chain: {err}")
        return 0

    return 1

def handle_deposit_event(event, contract_info_path="contract_info.json"):
    """Handle a Deposit event by calling wrap() on the destination chain."""
    print(f"[{datetime.utcnow()}] Handling Deposit event -> wrap() on destination")

    args = event["args"]
    token = Web3.to_checksum_address(args["token"])
    recipient = Web3.to_checksum_address(args["recipient"])
    amount = args["amount"]

    dest_w3 = connect_to("destination")
    contract_data = get_contract_info("destination", contract_info_path)
    if not contract_data:
        print("Missing destination contract info.")
        return

    contract = dest_w3.eth.contract(
        address=Web3.to_checksum_address(contract_data["address"]),
        abi=contract_data["abi"]
    )

    key = get_warden_key(contract_info_path)
    if not key:
        print("Warden key not available.")
        return
    if not key.startswith("0x"):
        key = "0x" + key

    account = dest_w3.eth.account.from_key(key)

    try:
        gas = contract.functions.wrap(token, recipient, amount).estimate_gas({
            "from": account.address
        })

        tx = contract.functions.wrap(token, recipient, amount).build_transaction({
            "from": account.address,
            "nonce": dest_w3.eth.get_transaction_count(account.address, "pending"),
            "gas": gas + 10000,
            "gasPrice": dest_w3.eth.gas_price
        })

        signed_tx = dest_w3.eth.account.sign_transaction(tx, key)
        tx_hash = dest_w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = dest_w3.eth.wait_for_transaction_receipt(tx_hash)

        print(f"[{datetime.utcnow()}] Wrap confirmed: {receipt['transactionHash'].hex()}")

    except Exception as err:
        print(f"Error wrapping tokens: {err}")

def handle_unwrap_event(event, contract_info_path="contract_info.json"):
    """Handle an Unwrap event by calling withdraw() on the source chain."""
    print(f"[{datetime.utcnow()}] Handling Unwrap event -> withdraw() on source")

    args = event["args"]
    token = Web3.to_checksum_address(args["underlying_token"])
    recipient = Web3.to_checksum_address(args["to"])
    amount = args["amount"]

    source_w3 = connect_to("source")
    contract_data = get_contract_info("source", contract_info_path)
    if not contract_data:
        print("Missing source contract info.")
        return

    contract = source_w3.eth.contract(
        address=Web3.to_checksum_address(contract_data["address"]),
        abi=contract_data["abi"]
    )

    key = get_warden_key(contract_info_path)
    if not key:
        print("Warden key not available.")
        return
    if not key.startswith("0x"):
        key = "0x" + key

    account = source_w3.eth.account.from_key(key)

    try:
        gas = contract.functions.withdraw(token, recipient, amount).estimate_gas({
            "from": account.address
        })

        tx = contract.functions.withdraw(token, recipient, amount).build_transaction({
            "from": account.address,
            "nonce": source_w3.eth.get_transaction_count(account.address, "pending"),
            "gas": gas + 10000,
            "gasPrice": source_w3.eth.gas_price
        })

        signed_tx = source_w3.eth.account.sign_transaction(tx, key)
        tx_hash = source_w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = source_w3.eth.wait_for_transaction_receipt(tx_hash)

        print(f"[{datetime.utcnow()}] Withdraw confirmed: {receipt['transactionHash'].hex()}")

    except Exception as err:
        print(f"Error withdrawing tokens: {err}")

if __name__ == "__main__":
    print(f"[{datetime.utcnow()}] Starting bridge scanner...")
    scan_blocks("source")
    scan_blocks("destination")