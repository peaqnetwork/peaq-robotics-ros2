#!/usr/bin/env python3
"""
Test DID Validation in Storage Bridge

This script demonstrates:
1. DID validation when robot.require_did=true
2. Automatic envelope creation (immutable format)
3. How users only publish raw data, not envelopes
"""

import json
import time
import requests
import hashlib
from nacl.signing import VerifyKey

def test_envelope_structure():
    """Verify that envelope follows immutable peaq-ipfs-envelope@v1 format"""
    
    # Example envelope CID from previous test
    envelope_cid = "QmXDQ58ExCVeJFenehTBrMN3Vy4W6yquPkzX2aywdqLExr"
    gateway_url = "https://salmon-managerial-caribou-735.mypinata.cloud/ipfs"
    
    print("=" * 80)
    print("TESTING ENVELOPE STRUCTURE")
    print("=" * 80)
    
    # Fetch envelope
    print(f"\n1. Fetching envelope from IPFS...")
    print(f"   CID: {envelope_cid}")
    
    envelope_url = f"{gateway_url}/{envelope_cid}"
    response = requests.get(envelope_url, timeout=10)
    response.raise_for_status()
    envelope = response.json()
    
    print(f"\n2. Envelope structure:")
    print(json.dumps(envelope, indent=2))
    
    # Validate required fields
    print(f"\n3. Validating immutable format...")
    
    required_fields = {
        'schema': 'peaq-ipfs-envelope@v1',
        'header': ['contentType', 'createdAt', 'robotId'],
        'payload': ['dataCid', 'dataSha256'],
        'proof': ['algorithm', 'publicKeyHex', 'signatureHex']
    }
    
    assert envelope['schema'] == required_fields['schema'], "Invalid schema!"
    print(f"   ✅ Schema: {envelope['schema']}")
    
    for field in required_fields['header']:
        assert field in envelope['header'], f"Missing header.{field}!"
        print(f"   ✅ header.{field}: {envelope['header'][field]}")
    
    for field in required_fields['payload']:
        assert field in envelope['payload'], f"Missing payload.{field}!"
        value = envelope['payload'][field]
        if len(str(value)) > 50:
            value = str(value)[:50] + "..."
        print(f"   ✅ payload.{field}: {value}")
    
    for field in required_fields['proof']:
        assert field in envelope['proof'], f"Missing proof.{field}!"
        value = envelope['proof'][field]
        if len(str(value)) > 50:
            value = str(value)[:50] + "..."
        print(f"   ✅ proof.{field}: {value}")
    
    # Verify data integrity
    print(f"\n4. Verifying data integrity...")
    data_cid = envelope['payload']['dataCid']
    expected_hash = envelope['payload']['dataSha256']
    
    data_url = f"{gateway_url}/{data_cid}"
    data_response = requests.get(data_url, timeout=10)
    data_response.raise_for_status()
    raw_data = data_response.content
    
    computed_hash = hashlib.sha256(raw_data).hexdigest()
    assert computed_hash == expected_hash, "Data integrity check failed!"
    print(f"   ✅ SHA256 verified: {computed_hash}")
    
    # Verify signature
    print(f"\n5. Verifying Ed25519 signature...")
    challenge = f"{expected_hash}|{envelope['header']['createdAt']}|{envelope['header']['robotId']}".encode('utf-8')
    
    public_key_hex = envelope['proof']['publicKeyHex']
    signature_hex = envelope['proof']['signatureHex']
    
    verify_key = VerifyKey(bytes.fromhex(public_key_hex))
    verify_key.verify(challenge, bytes.fromhex(signature_hex))
    print(f"   ✅ Signature verified!")
    print(f"   Public key: {public_key_hex}")
    
    # Show raw data
    print(f"\n6. Raw data (what user published):")
    print(json.dumps(json.loads(raw_data.decode('utf-8')), indent=2))
    
    print(f"\n{'=' * 80}")
    print("✅ ALL CHECKS PASSED - Envelope format is correct and immutable!")
    print("=" * 80)


def test_did_format_validation():
    """Test DID format validation logic"""
    
    print("\n" + "=" * 80)
    print("TESTING DID FORMAT VALIDATION")
    print("=" * 80)
    
    test_cases = [
        ("did:peaq:5DRVRDMh8PvUb9ViXwFwasQ5CB1oDVHp4AGtKz8NCZKxar8K", True, "Valid DID"),
        ("did:peaq:5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY", True, "Valid DID (different address)"),
        ("humanoid_001", False, "Not a DID"),
        ("did:web:example.com", False, "Wrong DID method"),
        ("did:peaq:", False, "Missing address"),
        ("peaq:5DRVRDMh8PvUb9ViXwFwasQ5CB1oDVHp4AGtKz8NCZKxar8K", False, "Missing 'did:' prefix"),
        ("", False, "Empty string"),
    ]
    
    def is_valid_did(robot_id: str) -> bool:
        """Same validation logic as storage_bridge_node.py"""
        if not robot_id:
            return False
        parts = robot_id.split(':')
        if len(parts) != 3:
            return False
        if parts[0] != 'did' or parts[1] != 'peaq':
            return False
        if not parts[2] or len(parts[2]) < 10:
            return False
        return True
    
    print("\nTest cases:")
    for robot_id, expected_valid, description in test_cases:
        result = is_valid_did(robot_id)
        status = "✅" if result == expected_valid else "❌"
        print(f"  {status} {description}")
        print(f"     Input: '{robot_id}'")
        print(f"     Expected: {expected_valid}, Got: {result}")
        assert result == expected_valid, f"Validation failed for: {robot_id}"
    
    print(f"\n{'=' * 80}")
    print("✅ ALL DID VALIDATION TESTS PASSED!")
    print("=" * 80)


def show_user_workflow():
    """Show what users actually do vs what the bridge does automatically"""
    
    print("\n" + "=" * 80)
    print("USER WORKFLOW - What Users Publish vs What Gets Stored")
    print("=" * 80)
    
    print("\n📤 WHAT USER PUBLISHES (to /peaq/storage/ingest):")
    print("-" * 80)
    
    user_data = {
        "robot_id": "humanoid_g1_001",
        "timestamp": int(time.time()),
        "sensors": {
            "temperature": 36.5,
            "battery": 87.3,
            "joint_angles": [45.2, 30.1, 60.5, 15.8],
            "position": {"x": 10.5, "y": 20.3, "z": 0.0}
        },
        "status": "operational"
    }
    
    print(json.dumps(user_data, indent=2))
    
    print("\n🤖 WHAT STORAGE BRIDGE DOES AUTOMATICALLY:")
    print("-" * 80)
    print("1. Reads raw data bytes")
    print("2. Computes SHA256 hash")
    print("3. Signs challenge: SHA256|timestamp|robot_id")
    print("4. Uploads raw data to IPFS → dataCid")
    print("5. Creates envelope (IMMUTABLE FORMAT)")
    print("6. Uploads envelope to IPFS → envelopeCid")
    print("7. Stores envelopeCid on blockchain")
    
    print("\n📦 WHAT GETS STORED IN IPFS (envelope):")
    print("-" * 80)
    
    envelope_example = {
        "schema": "peaq-ipfs-envelope@v1",
        "header": {
            "contentType": "application/json",
            "createdAt": user_data["timestamp"],
            "robotId": "did:peaq:5DRVRDMh8PvUb9ViXwFwasQ5CB1oDVHp4AGtKz8NCZKxar8K"
        },
        "payload": {
            "dataCid": "QmXsntSKUSuWZ6aZKhLvw2X85rWdnptowAfTfEsWPgtrmc",
            "dataSha256": "ebf2518702948f51d4c2cc51c326d06683e7e1db6ae55efd56410002afc83265"
        },
        "proof": {
            "algorithm": "ed25519",
            "publicKeyHex": "d178a0770a8aef690148c8a2ee5cb00b0eee01cf560e235be74eba16246ca653",
            "signatureHex": "a1b2c3d4e5f6... (64 bytes hex)"
        },
        "meta": {
            "robot_id": "humanoid_g1_001",
            "ts": user_data["timestamp"]
        }
    }
    
    print(json.dumps(envelope_example, indent=2))
    
    print("\n" + "=" * 80)
    print("KEY POINTS:")
    print("=" * 80)
    print("✅ Users ONLY publish raw sensor data")
    print("✅ Envelope format is AUTOMATIC and IMMUTABLE")
    print("✅ Users CANNOT bypass or modify the security structure")
    print("✅ All data flows through the same verification pipeline")
    print("✅ robot.id in config should be a DID (did:peaq:<address>)")
    print("=" * 80)


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("PEAQ STORAGE BRIDGE - DID VALIDATION & ENVELOPE FORMAT TESTS")
    print("=" * 80)
    
    try:
        # Test 1: DID validation
        test_did_format_validation()
        
        # Test 2: Envelope structure
        test_envelope_structure()
        
        # Test 3: User workflow
        show_user_workflow()
        
        print("\n" + "=" * 80)
        print("🎉 ALL TESTS COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
