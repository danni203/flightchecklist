# cycle_d_core.py
import time

DAG = {
    "node_id": "flight_ops", "name": "Project Icarus Flight Ops", "node_type": "root",
    "children": [
        {
            "node_id": "depot_prep", "name": "Depot Preparation", "node_type": "free_pool",
            "children": [
                {"node_id": "pack_bats", "name": "Pack Flight Batteries", "node_type": "leaf"},
                {"node_id": "inspect_frame", "name": "Airframe Inspection", "node_type": "leaf"}
            ]
        },
        {
            "node_id": "engine_runup", "name": "Engine Runup Sequence", "node_type": "linear_chain",
            "children": [
                {"node_id": "fuel_prime", "name": "Prime Fuel Lines", "node_type": "leaf"},
                {"node_id": "ignition", "name": "Ignition Test", "node_type": "leaf", "prerequisite": "fuel_prime"}
            ]
        },
        {
            "node_id": "pre_flight_barrier", "name": "Launch Synchronization Barrier", "node_type": "barrier",
            "prerequisites": ["depot_prep", "engine_runup"],
            "children": [
                {"node_id": "gps_lock", "name": "GPS 3D Fix", "node_type": "leaf", "ttl_minutes": 15}
            ]
        },
        {
            "node_id": "commander_authority", "name": "Final Launch Authority", "node_type": "approval",
            "prerequisite": "pre_flight_barrier"
        }
    ]
}

# 1. Globals, Indexes, & RBAC
MOCK_TIME = 0.0
LEDGER = []
NODE_INDEX = {}
STATE_MAP = {}

ROLES = {
    "tech_1": "OPERATOR",
    "tech_2": "OPERATOR",
    "hardware_sensor_1": "SYSTEM",
    "javaan": "COMMANDER"
}

def build_index(node):
    NODE_INDEX[node["node_id"]] = node
    for child in node.get("children", []):
        build_index(child)

build_index(DAG)

# 2. Time & Ledger Operations
def advance_time(minutes):
    global MOCK_TIME
    MOCK_TIME += (minutes * 60)

def log_event(action, node_id, actor, payload=""):
    LEDGER.append({
        "timestamp": MOCK_TIME,
        "action": action,
        "node_id": node_id,
        "actor": actor,
        "payload": payload
    })

# 3. Enhanced Evaluation Engine (RBAC & Approvals)
def cascade_block(node_id):
    node = NODE_INDEX[node_id]
    node["status"] = "BLOCKED"
    STATE_MAP[node_id] = "BLOCKED"
    for child in node.get("children", []):
        cascade_block(child["node_id"])

def evaluate_node(node_id):
    if node_id in STATE_MAP:
        return STATE_MAP[node_id]

    node = NODE_INDEX[node_id]
    node_type = node.get("node_type")
    base_status = "UNINITIALIZED"

    # Evaluate Children First
    children = node.get("children", [])
    child_statuses = [evaluate_node(child["node_id"]) for child in children]

    # Calculate Intrinsic Status
    if node_type == "leaf":
        latest_tick = next((e for e in reversed(LEDGER) if e["node_id"] == node_id and e["action"] == "TICK"), None)
        latest_auth_override = next((e for e in reversed(LEDGER) if e["node_id"] == node_id and e["action"] == "OVERRIDE" and ROLES.get(e["actor"]) == "COMMANDER"), None)
        
        # Evaluate Override precedence vs standard Tick
        if latest_auth_override and (not latest_tick or latest_auth_override["timestamp"] >= latest_tick["timestamp"]):
            base_status = "GREEN_OVR"
        elif latest_tick:
            if "ttl_minutes" in node:
                age_minutes = (MOCK_TIME - latest_tick["timestamp"]) / 60.0
                if age_minutes > node["ttl_minutes"]:
                    base_status = "AMBER"
                else:
                    base_status = "GREEN"
            else:
                base_status = "GREEN"
                
    elif node_type == "approval":
        latest_approve = next((e for e in reversed(LEDGER) if e["node_id"] == node_id and e["action"] == "APPROVE"), None)
        if latest_approve and ROLES.get(latest_approve["actor"]) == "COMMANDER":
            base_status = "GREEN"
        else:
            base_status = "STAGED"
            
    else:
        if not children:
            base_status = "UNINITIALIZED"
        elif any(s == "BLOCKED" for s in child_statuses):
            base_status = "BLOCKED"
        elif any(s == "AMBER" for s in child_statuses):
            base_status = "AMBER"
        elif all(s in ["GREEN", "GREEN_OVR"] for s in child_statuses):
            base_status = "GREEN"
        elif any(s in ["GREEN", "GREEN_OVR", "ACTIVE"] for s in child_statuses):
            base_status = "ACTIVE"

    # Apply Barrier & Lateral Dependency Logic
    reqs = []
    if "prerequisite" in node: reqs.append(node["prerequisite"])
    if "prerequisites" in node: reqs.extend(node["prerequisites"])

    local_block = False
    for req_id in reqs:
        req_status = evaluate_node(req_id)
        if req_status not in ["GREEN", "GREEN_OVR"]:
            local_block = True
            break

    if local_block:
        base_status = "BLOCKED"
        for child in children:
            cascade_block(child["node_id"])

    STATE_MAP[node_id] = base_status
    node["status"] = base_status
    return base_status

def evaluate_graph():
    STATE_MAP.clear()
    evaluate_node(DAG["node_id"])

# 4. ASCII Renderer
def render_tree(node, indent=0):
    colors = {
        "UNINITIALIZED": "\033[90m[ ]\033[0m", 
        "ACTIVE": "\033[94m[-]\033[0m", 
        "GREEN": "\033[92m[✓]\033[0m", 
        "GREEN_OVR": "\033[96m[O]\033[0m", 
        "AMBER": "\033[93m[!]\033[0m", 
        "BLOCKED": "\033[91m[X]\033[0m",
        "STAGED": "\033[95m[?]\033[0m"     
    }
    meta = []
    if "ttl_minutes" in node: meta.append(f"TTL:{node['ttl_minutes']}m")
    meta_str = f" \033[90m({', '.join(meta)})\033[0m" if meta else ""
    
    print(f"{'    ' * indent}{colors.get(node.get('status', 'UNINITIALIZED'))} {node['name']}{meta_str}")
    for child in node.get("children", []):
        render_tree(child, indent + 1)

# 5. Temporal Self-Test Harness
def run_self_test():
    print("\n\033[1m--- CYCLE D: RBAC & TWO-PHASE COMMIT ---\033[0m")
    
    log_event("TICK", "pack_bats", "tech_1")
    log_event("TICK", "inspect_frame", "tech_1")
    log_event("TICK", "fuel_prime", "tech_2")
    log_event("TICK", "ignition", "tech_2")
    log_event("TICK", "gps_lock", "hardware_sensor_1")
    advance_time(16)
    
    print("State: GPS has expired. Pre-Flight Barrier is degraded.")
    
    print("Test 4: Tech attempts to override expired GPS...")
    log_event("OVERRIDE", "gps_lock", "tech_1", payload="Looks fine to me")
    evaluate_graph()
    assert NODE_INDEX["gps_lock"]["status"] == "AMBER", "Failure: Tech should not be able to override."
    print("Test 4 Passed: Evaluator rejected unauthorized override.")

    print("Test 5: Commander overrides expired GPS...")
    log_event("OVERRIDE", "gps_lock", "javaan", payload="Known drift in hangar, physical verification confirms lock.")
    evaluate_graph()
    assert NODE_INDEX["gps_lock"]["status"] == "GREEN_OVR", "Failure: Commander override failed."
    assert NODE_INDEX["commander_authority"]["status"] == "STAGED", "Failure: Approval should be staged."
    print("Test 5 Passed: Commander override forced barrier open. Final Launch Authority is now STAGED [?].")

    print("Test 6: Commander issues final APPROVE action...")
    log_event("APPROVE", "commander_authority", "javaan")
    evaluate_graph()
    assert NODE_INDEX["flight_ops"]["status"] == "GREEN", "Failure: Flight Ops should be fully Green."
    print("Test 6 Passed: Two-Phase commit complete. Flight Ops cleared.")

    print("\n\033[1m=== FINAL CLEARANCE ARRAY ===\033[0m")
    render_tree(DAG)
    print("\n")

if __name__ == "__main__":
    run_self_test()
