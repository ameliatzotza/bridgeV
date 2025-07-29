import os
import json
from web3 import Web3
from dotenv import load_dotenv
from solcx import compile_standard, install_solc

load_dotenv()

install_solc("0.8.20")

SOURCE_PATH = "Bridge/src/Source.sol"
DEST_PATH = "Bridge/src/Destination.sol"
OZ_PATH = "./"

AVAX_RPC = os.getenv("AVAX_RPC")
BNB_RPC = os.getenv("BNB_RPC")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

assert PRIVATE_KEY, "Missing PRIVATE_KEY in .env"

def compile_contract(path, contract_name):
    with open(path, "r") as file:
        source_code = file.read()

    compiled = compile_standard({
        "language": "Solidity",
        "sources": {
            path: {
                "content": source_code
            }
        },
        "settings": {
          "remappings": [
            "openzeppelin/=./openzeppelin/contracts/"
            ],
            "outputSelection": {
                "*": {
                    "*": ["abi", "evm.bytecode"]
                }
            }
        }
    }, solc_version="0.8.20", base_path=".")

    contract = compiled["contracts"][path][contract_name]
    abi = contract["abi"]
    bytecode = contract["evm"]["bytecode"]["object"]
    return abi, bytecode

def deploy(web3, abi, bytecode):
    account = web3.eth.account.from_key(PRIVATE_KEY)
    contract = web3.eth.contract(abi=abi, bytecode=bytecode)

    txn = contract.constructor().build_transaction({
        "from": account.address,
        "nonce": web3.eth.get_transaction_count(account.address),
        "gas": 2_000_000,
        "gasPrice": web3.eth.gas_price
    })

    signed = account.sign_transaction(txn)
    tx_hash = web3.eth.send_raw_transaction(signed.rawTransaction)
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt.contractAddress

print("🛠️ Compiling and deploying Source.sol...")
src_abi, src_bytecode = compile_contract(SOURCE_PATH, "Source")
w3_avax = Web3(Web3.HTTPProvider(AVAX_RPC))
src_address = deploy(w3_avax, src_abi, src_bytecode)
print(f"✅ Source.sol deployed to Avalanche: {src_address}")

print("\n🛠️ Compiling and deploying Destination.sol...")
dest_abi, dest_bytecode = compile_contract(DEST_PATH, "Destination")
w3_bnb = Web3(Web3.HTTPProvider(BNB_RPC))
dest_address = deploy(w3_bnb, dest_abi, dest_bytecode)
print(f"✅ Destination.sol deployed to BNB: {dest_address}")

print("\n💾 Writing to contract_info.json...")
contract_info = {
    "source": {
        "address": src_address,
        "abi": src_abi
    },
    "destination": {
        "address": dest_address,
        "abi": dest_abi
    }
}

with open("contract_info.json", "w") as f:
    json.dump(contract_info, f, indent=2)

print("✅ Deployment complete! Saved to contract_info.json.")
