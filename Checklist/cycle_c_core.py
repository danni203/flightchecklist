# cycle_c_core.py
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
        }
    ]
}

# 1. Globals & Indexes
MOCK_TIME = 0.0
LEDGER = []
NODE_INDEX = {}
STATE_MAP = {}

def build_index(node):
    """Flattens the DAG into a lookup table for dependency resolution."""
    NODE_INDEX[node["node_id"]] = node
    for child in node.get("children", []):
        build_index(child)

build_index(DAG)

# 2. Time & Ledger Operations
def advance_time(minutes):
    global MOCK_TIME
    MOCK_TIME += (minutes * 60)

def log_event(action, node_id, actor):
    LEDGER.append({
        "timestamp": MOCK_TIME,
        "action": action,
        "node_id": node_id,
        "actor": actor
    })

# 3. Enhanced Evaluation Engine with Top-Down Cascade
def cascade_block(node_id):
    """Recursively forces all children to BLOCKED if their parent is locked."""
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
        if latest_tick:
            if "ttl_minutes" in node:
                age_minutes = (MOCK_TIME - latest_tick["timestamp"]) / 60.0
                if age_minutes > node["ttl_minutes"]:
                    base_status = "AMBER"
                else:
                    base_status = "GREEN"
            else:
                base_status = "GREEN"
    else:
        if not children:
            base_status = "UNINITIALIZED"
        elif any(s == "BLOCKED" for s in child_statuses):
            base_status = "BLOCKED"
        elif any(s == "AMBER" for s in child_statuses):
            base_status = "AMBER"
        elif all(s == "GREEN" for s in child_statuses):
            base_status = "GREEN"
        elif any(s in ["GREEN", "ACTIVE"] for s in child_statuses):
            base_status = "ACTIVE"

    # Apply Barrier & Lateral Dependency Logic
    reqs = []
    if "prerequisite" in node: reqs.append(node["prerequisite"])
    if "prerequisites" in node: reqs.extend(node["prerequisites"])

    local_block = False
    for req_id in reqs:
        req_status = evaluate_node(req_id)
        if req_status not in ["GREEN", "STAGED"]:
            local_block = True
            break

    # If lateral prerequisites fail, block this node and cascade downward
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
        "UNINITIALIZED": "\033[90m[ ]\033[0m", "ACTIVE": "\033[94m[-]\033[0m", 
        "GREEN": "\033[92m[✓]\033[0m", "AMBER": "\033[93m[!]\033[0m", "BLOCKED": "\033[91m[X]\033[0m"
    }
    meta = []
    if "ttl_minutes" in node: meta.append(f"TTL:{node['ttl_minutes']}m")
    meta_str = f" \033[90m({', '.join(meta)})\033[0m" if meta else ""
    
    print(f"{'    ' * indent}{colors.get(node.get('status', 'UNINITIALIZED'))} {node['name']}{meta_str}")
    for child in node.get("children", []):
        render_tree(child, indent + 1)

# 5. Temporal Self-Test Harness
def run_self_test():
    print("\n\033[1m--- CYCLE C: TEMPORAL & BARRIER VALIDATION ---\033[0m")
    
    # Test 1: Barrier Enforcement
    log_event("TICK", "gps_lock", "hardware_sensor_1")
    evaluate_graph()
    assert NODE_INDEX["gps_lock"]["status"] == "BLOCKED", "Failure: GPS Lock should be BLOCKED by unmet barrier."
    print("Test 1 Passed: Downstream execution blocked by barrier.")

    # Test 2: Fulfill Prerequisites
    log_event("TICK", "pack_bats", "tech_1")
    log_event("TICK", "inspect_frame", "tech_1")
    log_event("TICK", "fuel_prime", "tech_2")
    log_event("TICK", "ignition", "tech_2")
    
    # Tick GPS again now that barriers are theoretically clear
    log_event("TICK", "gps_lock", "hardware_sensor_1")
    evaluate_graph()
    assert NODE_INDEX["pre_flight_barrier"]["status"] == "GREEN", "Failure: Barrier should clear."
    print("Test 2 Passed: Barrier clears upon prerequisite fulfillment.")

    # Test 3: TTL Expiration and Cascading Regression
    print("Test 3: Advancing MOCK_TIME by 16 minutes...")
    advance_time(16)
    evaluate_graph()
    assert NODE_INDEX["gps_lock"]["status"] == "AMBER", "Failure: GPS Lock should expire to AMBER."
    assert NODE_INDEX["flight_ops"]["status"] == "AMBER", "Failure: Root node should reflect degraded state."
    print("Test 3 Passed: TTL expiration triggered cascading regression up the DAG.")

    print("\n\033[1m=== DEGRADED STATE ARRAY ===\033[0m")
    render_tree(DAG)
    print("\n")

if __name__ == "__main__":
    run_self_test()
