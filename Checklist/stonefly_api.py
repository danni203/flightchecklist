# stonefly_api.py
import os
import json
import base64
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn
from typing import Optional
from stonefly_node import StoneflyDaemon
from cryptography.hazmat.primitives.asymmetric import ed25519

app = FastAPI(title="STONEFLY Checklist Engine API", version="1.0")

# Network Configuration
NODE_ID = os.environ.get("NODE_ID", "ALPHA_API")
IPC_PORT = int(os.environ.get("IPC_PORT", 5010))
GOSSIP_PORT = int(os.environ.get("GOSSIP_PORT", 6010))
WEB_PORT = int(os.environ.get("WEB_PORT", 8000))

# --- IMPORTANT: Paste your newest Root Key here ---
ROOT_PUB_KEY_B64 = "XlcdSojY+2X6PTNiuOYRmu/+aROjtE1FzFY0rH8l+lU=" 

engine = StoneflyDaemon(node_id=NODE_ID, ipc_port=IPC_PORT, gossip_port=GOSSIP_PORT)

# --- Pydantic V2 Schemas ---
class IdentityPayload(BaseModel):
    crew_id: str
    role: str
    pub_key: str

class CredentialPackage(BaseModel):
    identity: IdentityPayload
    root_signature: str

class ActionPayload(BaseModel):
    action: str
    target: str
    actor: str
    actor_role: str 
    payload: Optional[str] = ""

# --- RBAC Ownership Map ---
TASK_OWNERS = {
    "pack_bats": ["OPERATOR"],
    "payload": ["OPERATOR", "PILOT"],
    "als_auth": ["PILOT", "COMMANDER"],
    "auth": ["COMMANDER"]
}

@app.get("/")
def serve_frontend():
    return FileResponse("index.html")

@app.post("/auth")
def authenticate_operator(pkg: CredentialPackage):
    try:
        root_bytes = base64.b64decode(ROOT_PUB_KEY_B64)
        root_public_key = ed25519.Ed25519PublicKey.from_public_bytes(root_bytes)
        
        identity_dict = pkg.identity.model_dump() # Pydantic V2 Fix
        payload_bytes = json.dumps(identity_dict, sort_keys=True).encode('utf-8')
        signature_bytes = base64.b64decode(pkg.root_signature)
        
        root_public_key.verify(signature_bytes, payload_bytes)
        
        return {
            "status": "AUTHORIZED",
            "crew_id": identity_dict["crew_id"],
            "role": identity_dict["role"]
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail="CRITICAL: Cryptographic Signature Invalid or Forged.")

@app.get("/state")
def get_state():
    try:
        return engine.evaluate()
    except Exception as e:
        import traceback
        traceback.print_exc() # Prints the exact line of the crash to your terminal
        raise HTTPException(status_code=500, detail=f"Engine Evaluation Error: {str(e)}")

@app.post("/action")
def submit_action(req: ActionPayload):
    valid_actions = ["TICK", "FAIL", "OUT", "OVERRIDE", "APPROVE", "INIT_SESSION"]
    if req.action not in valid_actions:
        raise HTTPException(status_code=400, detail="Invalid action.")

    # Strict RBAC Gatekeeper
    if req.action in ["TICK", "APPROVE"]:
        allowed_roles = TASK_OWNERS.get(req.target, [])
        if allowed_roles and req.actor_role not in allowed_roles:
            raise HTTPException(
                status_code=403, 
                detail=f"ACCESS DENIED. Task '{req.target}' requires roles: {allowed_roles}"
            )
        
    try:
        engine.log_event(action=req.action, target=req.target, actor=req.actor, payload=req.payload)
        return engine.evaluate()
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    print(f"\033[96m[*] Booting STONEFLY Headless API [{NODE_ID}] on port {WEB_PORT}...\033[0m")
    # Split-Brain Fix: Only the Master Node generates the session ID
    if NODE_ID == "ALPHA_API":
        engine.log_event("INIT_SESSION", "system", "admin")
    uvicorn.run(app, host="0.0.0.0", port=WEB_PORT)
