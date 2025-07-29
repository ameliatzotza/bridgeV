import json
from web3 import Web3
from solcx import compile_standard, install_solc

# Set your private key here (testnet only!)
PRIVATE_KEY = "0x62fa8b75288b4bfcddafcf568cafe86850e74a693cbdeb940c178fb52a5f29fe"
ACCOUNT_ADDRESS = Web3.to_checksum_address(Web3().eth.account.from_key(PRIVATE_KEY).address)

# File paths
SOURCE_PATH = "Bridge/src/Source.sol"
DEST_PATH = "Bridge/src/Destination.sol"

def compile_contract(path, contract_name):
    with open(path, 'r') as f:
        source_code = f.read()

    install_solc("0.8.20")

    compiled = compile_standard({
        "language": "Solidity",
        "sources": {
            path: {"content": source_code}
        },
        "settings": {
            "outputSelection": {
                "*": {
                    "*": ["abi", "evm.bytecode.object"]
                }
            },
            "remappings": [
                "@openzeppelin/=./openzeppelin/"
            ]
        }
    }, solc_version="0.8.20", base_path="./")

    contract = compiled['contracts'][path][contract_name]
    return contract['abi'], contract['evm']['bytecode']['object']

def deploy_contract(w3, abi, bytecode):
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    nonce = w3.eth.get_transaction_count(ACCOUNT_ADDRESS)
    
    tx = contract.constructor(ACCOUNT_ADDRESS).build_transaction({
        'from': ACCOUNT_ADDRESS,
        'nonce': nonce,
        'gasPrice': w3.eth.gas_price,
        'gas': 5000000
    })
    
    signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    return receipt.contractAddress

if __name__ == "__main__":
    print("🛠️ Compiling and deploying Source.sol...")
    src_abi, src_bytecode = compile_contract(SOURCE_PATH, "Source")
    w3_source = Web3(Web3.HTTPProvider("https://api.avax-test.network/ext/bc/C/rpc"))
    src_address = deploy_contract(w3_source, src_abi, src_bytecode)
    print(f"✅ Source contract deployed at: {src_address}")

    print("🛠️ Compiling and deploying Destination.sol...")
    dst_abi, dst_bytecode = compile_contract(DEST_PATH, "Destination")
    w3_dest = Web3(Web3.HTTPProvider("https://data-seed-prebsc-1-s1.binance.org:8545/"))
    dst_address = deploy_contract(w3_dest, dst_abi, dst_bytecode)
    print(f"✅ Destination contract deployed at: {dst_address}")

    # Save info
    with open("contract_info.json", "w") as f:
        json.dump({
            "source": {"address": src_address, "abi": src_abi},
            "destination": {"address": dst_address, "abi": dst_abi}
        }, f, indent=2)
