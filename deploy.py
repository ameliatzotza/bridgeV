import os
import json
from web3 import Web3
from eth_account import Account

def connect_to(chain):
    urls = {
        "avax": "https://api.avax-test.network/ext/bc/C/rpc",
        "bsc": "https://data-seed-prebsc-1-s1.binance.org:8545"
    }
    return Web3(Web3.HTTPProvider(urls[chain]))

def load_compiled_contract(path):
    with open(path) as f:
        contract_json = json.load(f)
        return contract_json['abi'], contract_json['bytecode']

def deploy_contract(chain, abi, bytecode):
    w3 = connect_to(chain)
    acct = Account.from_key(os.getenv("WARDEN_PRIVATE_KEY"))

    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx = contract.constructor(acct.address).build_transaction({
        'from': acct.address,
        'nonce': w3.eth.get_transaction_count(acct.address),
        'gas': 3000000,
        'gasPrice': w3.eth.gas_price,
        'chainId': w3.eth.chain_id
    })

    signed_tx = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    print(f"{chain} contract deployed at: {receipt.contractAddress}")
    return receipt.contractAddress

if __name__ == "__main__":
    source_abi, source_bytecode = load_compiled_contract("out/Source.json")
    dest_abi, dest_bytecode = load_compiled_contract("out/Destination.json")

    source_address = deploy_contract("avax", source_abi, source_bytecode)
    dest_address = deploy_contract("bsc", dest_abi, dest_bytecode)

    # Save updated contract_info.json
    with open("contract_info.json", "r") as f:
        data = json.load(f)

    data["source"]["address"] = source_address
    data["destination"]["address"] = dest_address

    with open("contract_info.json", "w") as f:
        json.dump(data, f, indent=2)

    print("✅ contract_info.json updated.")
    