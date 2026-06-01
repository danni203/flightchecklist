# stonefly_pki.py
# stonefly_pki.py
import json
import base64
import qrcode
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

def generate_keypair():
    """Generates an Ed25519 Private/Public key pair."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key

def serialize_public_key(public_key):
    """Converts a public key to a base64 string for easy transmission."""
    raw_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    return base64.b64encode(raw_bytes).decode('utf-8')

def sign_payload(private_key, payload_dict):
    """Signs a JSON payload using the provided private key."""
    payload_bytes = json.dumps(payload_dict, sort_keys=True).encode('utf-8')
    signature = private_key.sign(payload_bytes)
    return base64.b64encode(signature).decode('utf-8')

if __name__ == "__main__":
    print("\n\033[1m=== STONEFLY AIR-GAPPED PKI GENERATOR ===\033[0m")
    
    # 1. Generate ONE Master Root Authority for the entire fleet
    root_private, root_public = generate_keypair()
    root_pub_str = serialize_public_key(root_public)
    
    print("\n\033[93mCRITICAL STEP:\033[0m")
    print("Copy the string below and paste it into stonefly_api.py as ROOT_PUB_KEY_B64:")
    print(f"\033[92m{root_pub_str}\033[0m\n")

    # 2. Define the exact roster to match the API Gatekeeper
    crew_roster = [
        {"crew_id": "OP-JAVAAN-01", "role": "COMMANDER"}, # Has Final Launch Authority
        {"crew_id": "TECH-ALPHA",   "role": "OPERATOR"},  # Handles Depot/Batteries
        {"crew_id": "PILOT-BRAVO",  "role": "PILOT"}      # Handles Telemetry
    ]

    print("\033[96mGenerating Cryptographic Badges...\033[0m")
    for operator in crew_roster:
        # Generate a unique private key for this specific operator
        user_private, user_public = generate_keypair()
        operator["pub_key"] = serialize_public_key(user_public)
        
        # The Root Authority signs the operator's payload
        signature = sign_payload(root_private, operator)
        credential_package = {"identity": operator, "root_signature": signature}
        
        # Generate the physical QR Code Badge
        qr = qrcode.QRCode(
            version=1, 
            error_correction=qrcode.constants.ERROR_CORRECT_L, 
            box_size=10, 
            border=4
        )
        qr.add_data(json.dumps(credential_package, separators=(',', ':')))
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        filename = f"{operator['crew_id']}_badge.png"
        img.save(filename)
        
        print(f"[✓] Created: {filename} (Role: {operator['role']})")
