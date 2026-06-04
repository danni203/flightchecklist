# stonefly_api.py
import os
import json
import base64
import threading # For the Ghost Crew background thread
import time      #  For Ghost Crew delays
import random    #  For randomized AI clicks
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


# GHOST CREW AUTOPILOT LOGIC ---
# Using a dictionary makes this thread-safe and immune to global scope errors
GHOST_STATE = {"active": False}

def ghost_crew_loop():
    """Background AI thread that automatically completes available tasks."""
    while True:
        if GHOST_STATE["active"]:
            try:
                state = engine.evaluate()
                
                # Find all tasks that are currently available to be ticked
                available_tasks = []
                for task_id, status in state.items():
                    if status in ["UNINITIALIZED", "ACTIVE", "STAGED"] and task_id not in ["op_icarus_tactical", "phase_1_depot", "phase_2_transit", "phase_3_gcs", "phase_5_airframe", "phase_6_launch", "phase_7_recovery", "phase_8_rtb"]:
                        available_tasks.append(task_id)

                if available_tasks:
                    # Pick a random available task
                    target = random.choice(available_tasks)
                    # Use a bypass actor ID to show it was the AI
                    engine.log_event(action="TICK", target=target, actor="AI_GHOST_CREW", payload="")
                    print(f"\033[95m[GHOST CREW] Auto-Ticked: {target}\033[0m")
                    
            except Exception as e:
                print(f"Ghost Crew Error: {e}")
                
        # Wait 3 to 6 seconds before making the next move
        time.sleep(random.uniform(3.0, 6.0))

# Start the Ghost Crew thread in the background
threading.Thread(target=ghost_crew_loop, daemon=True).start()

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
# --- RBAC Ownership Map for Operation Icarus ---
TASK_OWNERS = {
    "tool_packing": ["OPERATOR"], "airframe_manifest": ["OPERATOR"], "ups_charge": ["OPERATOR"], "crypto_sync": ["COMMANDER"],
    "convoy_arrive": ["OPERATOR"], "arrival_audit": ["COMMANDER"], "perimeter_sec": ["OPERATOR"],
    "gen_power": ["OPERATOR"], "starlink_lock": ["COMMANDER"], "tac_rf_mast": ["OPERATOR"], "gcs_boot": ["COMMANDER"], "rem_hotspot": ["PILOT"], "voice_comms": ["COMMANDER"],
    "wing_spars": ["OPERATOR"], "load_bats": ["OPERATOR"], "fcu_power": ["OPERATOR"], "telemetry_link": ["PILOT"], "rc_link": ["PILOT"], "gps_3d_fix": ["PILOT"],
    "car_rigged": ["OPERATOR"], "release_test": ["OPERATOR"], "mount_airframe": ["OPERATOR"], 
    "launch_auth": ["COMMANDER"], "launch_emcon": ["COMMANDER"], "car_speed": ["OPERATOR"], "release_mech": ["OPERATOR"], "car_rtb": ["OPERATOR"], "emcon_drop": ["OPERATOR"], "climb_out": ["PILOT"],
    "clear_airspace": ["PILOT"], "engine_cut": ["PILOT"], "disarm_fcu": ["OPERATOR"], "data_offload": ["COMMANDER"], "site_sterile": ["OPERATOR"], "convoy_rtb": ["OPERATOR"], "mission_close": ["COMMANDER"]
}
@app.get("/")
def serve_frontend():
    return FileResponse("dashboard.html")
    
    
# Endpoint to toggle the Ghost Crew ---
@app.post("/toggle_ghost")
def toggle_ghost():
    # Flip the boolean inside the dictionary
    GHOST_STATE["active"] = not GHOST_STATE["active"]
    status = "ENGAGED" if GHOST_STATE["active"] else "DISENGAGED"
    return {"message": f"Ghost Crew {status}", "active": GHOST_STATE["active"]}
    
    
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
