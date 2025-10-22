#!/usr/bin/env python3
from peaq_robot.utils.keystore import load_keystore
from substrateinterface import Keypair

PATH = "/root/.peaq_robot/wallet.json"
try:
    st, payload = load_keystore(PATH)
    if st == "mnemonic":
        kp = Keypair.create_from_mnemonic(payload)
    else:
        kp = Keypair.create_from_private_key(payload)
    print("WALLET_ADDR:", kp.ss58_address)
except Exception as e:
    print("WALLET_ERR:", e)


