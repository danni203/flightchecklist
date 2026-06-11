# stonefly_api.py
import os
import json
import base64
import threading
import time
import random
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn
from typing import Optional
from stonefly_node import StoneflyDaemon
from cryptography.hazmat.primitives.asymmetric import ed25519

app = FastAPI(title="STONEFLY Checklist Engine API", version="1.0")

# --- 1. NETWORK CONFIGURATION ---
NODE_ID = os.environ.get("NODE_ID", "ALPHA_API")
IPC_PORT = int(os.environ.get("IPC_PORT", 5010))
GOSSIP_PORT = int(os.environ.get("GOSSIP_PORT", 6010))
WEB_PORT = int(os.environ.get("WEB_PORT", 8000))

# 🔴 CRITICAL: Paste your Root Key from stonefly_pki.py here 🔴
ROOT_PUB_KEY_B64 = "LtpWXSevKjB6dwvIHf0jhdI1yxoOCuUMYWtpJdYqgaA=" 

engine = StoneflyDaemon(node_id=NODE_ID, ipc_port=IPC_PORT, gossip_port=GOSSIP_PORT)

# --- 2. GHOST CREW AUTOPILOT (Human-on-the-Loop) ---
GHOST_STATE = {"active": False}

def ghost_crew_loop():
    """Background AI thread that completes grunt work but waits for human approval."""
    while True:
        if GHOST_STATE["active"]:
            try:
                payload = engine.evaluate()
                dag = payload.get("dag", {})
                
                available_tasks = []

                # Recursively walk the nested DAG
                def walk(node):
                    # --- CHANGED: The AI now strictly ignores "approval" nodes! ---
                    if node.get("node_type") == "leaf":
                        if node.get("status") in ["UNINITIALIZED", "ACTIVE", "STAGED"]:
                            available_tasks.append(node["node_id"])
                    
                    for child in node.get("children", []):
                        walk(child)

                walk(dag)

                if available_tasks:
                    # Pick a random available leaf task
                    target = random.choice(available_tasks)
                    
                    # The AI acts as a standard grunt worker
                    engine.log_event(action="TICK", target=target, actor="GHOST_CREW", payload="")
                    print(f"\033[95m[GHOST CREW] Auto-Ticked: {target}\033[0m")
                    
            except Exception as e:
                print(f"Ghost Crew Error: {e}")
                
        # Wait 3 to 6 seconds before making the next move
        time.sleep(random.uniform(3.0, 6.0))

threading.Thread(target=ghost_crew_loop, daemon=True).start()

# --- 3. PYDANTIC SCHEMAS ---
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

# --- 4. RBAC GATEKEEPER MAPPING ---
TASK_OWNERS = {
    "weather_check": ["COMMANDER", "PILOT"], "brief_crew": ["COMMANDER"],
    "tool_packing": ["OPERATOR"], "airframe_manifest": ["OPERATOR"], "ups_charge": ["OPERATOR"], "crypto_sync": ["COMMANDER"],
    "convoy_arrive": ["OPERATOR"], "arrival_audit": ["COMMANDER"], "perimeter_sec": ["OPERATOR"],
    "gen_power": ["OPERATOR"], "starlink_lock": ["COMMANDER"], "tac_rf_mast": ["OPERATOR"], "gcs_boot": ["COMMANDER"], "rem_hotspot": ["PILOT"], "voice_comms": ["COMMANDER"],
    "wing_spars": ["OPERATOR"], "load_bats": ["OPERATOR"], "fcu_power": ["OPERATOR"], "telemetry_link": ["PILOT"], "rc_link": ["PILOT"], "gps_3d_fix": ["PILOT"],
    "car_rigged": ["OPERATOR"], "release_test": ["OPERATOR"], "mount_airframe": ["OPERATOR"], 
    "launch_auth": ["COMMANDER"], "launch_emcon": ["COMMANDER"], "car_speed": ["OPERATOR"], "release_mech": ["OPERATOR"], "car_rtb": ["OPERATOR"], "emcon_drop": ["OPERATOR"], "climb_out": ["PILOT"],
    "clear_airspace": ["PILOT"], "engine_cut": ["PILOT"], "disarm_fcu": ["OPERATOR"], "data_offload": ["COMMANDER"], "site_sterile": ["OPERATOR"], "convoy_rtb": ["OPERATOR"], "mission_close": ["COMMANDER"]
}

# --- 5. FASTAPI ROUTES ---

@app.get("/")
def serve_frontend():
    # 🟢 This is the bridge! It tells FastAPI to serve your new GUI 🟢
    return FileResponse("dashboard.html")

@app.post("/toggle_ghost")
def toggle_ghost():
    GHOST_STATE["active"] = not GHOST_STATE["active"]
    return {"message": "Toggled", "active": GHOST_STATE["active"]}

@app.post("/auth")
def authenticate_operator(pkg: CredentialPackage):
    try:
        root_bytes = base64.b64decode(ROOT_PUB_KEY_B64)
        root_public_key = ed25519.Ed25519PublicKey.from_public_bytes(root_bytes)
        
        identity_dict = pkg.identity.model_dump()
        payload_bytes = json.dumps(identity_dict, sort_keys=True).encode('utf-8')
        signature_bytes = base64.b64decode(pkg.root_signature)
        
        root_public_key.verify(signature_bytes, payload_bytes)
        return {"status": "AUTHORIZED", "crew_id": identity_dict["crew_id"], "role": identity_dict["role"]}
    except Exception:
        raise HTTPException(status_code=401, detail="CRITICAL: Cryptographic Signature Invalid.")

@app.get("/state")
def get_state():
    return engine.evaluate()

@app.post("/action")
def submit_action(req: ActionPayload):
    if req.action not in ["TICK", "FAIL", "OUT", "OVERRIDE", "APPROVE", "INIT_SESSION"]:
        raise HTTPException(status_code=400, detail="Invalid action.")

    if req.action in ["TICK", "APPROVE"]:
        allowed_roles = TASK_OWNERS.get(req.target, [])
        if allowed_roles and req.actor_role not in allowed_roles:
            raise HTTPException(status_code=403, detail=f"Requires roles: {allowed_roles}")
        
    try:
        engine.log_event(action=req.action, target=req.target, actor=req.actor, payload=req.payload)
        return engine.evaluate()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    print(f"\033[96m[*] Booting STONEFLY Tactical API [{NODE_ID}] on port {WEB_PORT}...\033[0m")
    if NODE_ID == "ALPHA_API":
        engine.log_event("INIT_SESSION", "system", "admin")
    uvicorn.run(app, host="0.0.0.0", port=WEB_PORT)