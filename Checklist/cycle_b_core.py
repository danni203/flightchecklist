# cycle_b_core.py
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
        }
    ]
}

# 1. The Immutable Ledger
LEDGER = []

def log_event(action, node_id, actor):
    """Appends a deterministic event to the ledger."""
    LEDGER.append({
        "timestamp": time.time(),
        "action": action,
        "node_id": node_id,
        "actor": actor
    })

# 2. The Evaluation Engine
def evaluate_node(node):
    """Materializes state by evaluating the ledger against the DAG topology."""
    node_type = node.get("node_type")
    
    # Base Case: Leaf Nodes
    if node_type == "leaf":
        # Check if a TICK event exists in the ledger for this node
        is_ticked = any(e["node_id"] == node["node_id"] and e["action"] == "TICK" for e in LEDGER)
        node["status"] = "GREEN" if is_ticked else "UNINITIALIZED"
        return node["status"]

    # Recursive Case: Composite Nodes
    children = node.get("children", [])
    child_statuses = [evaluate_node(child) for child in children]
    
    if not children:
        node["status"] = "UNINITIALIZED"
    elif all(status == "GREEN" for status in child_statuses):
        node["status"] = "GREEN"
    elif any(status in ["GREEN", "ACTIVE"] for status in child_statuses):
        node["status"] = "ACTIVE"
    else:
        node["status"] = "UNINITIALIZED"
        
    return node["status"]

# 3. ASCII Renderer (Simplified for brevity)
def render_tree(node, indent=0):
    colors = {"UNINITIALIZED": "\033[90m[ ]\033[0m", "ACTIVE": "\033[94m[-]\033[0m", "GREEN": "\033[92m[✓]\033[0m"}
    print(f"{'    ' * indent}{colors.get(node.get('status', 'UNINITIALIZED'))} {node['name']}")
    for child in node.get("children", []):
        render_tree(child, indent + 1)

# 4. Self-Test Harness
def run_self_test():
    print("\n\033[1m--- INITIALIZING TEST HARNESS ---\033[0m")
    
    # Test 1: Tick one item in a free pool
    log_event("TICK", "pack_bats", "human_operator_1")
    evaluate_node(DAG)
    assert DAG["children"][0]["status"] == "ACTIVE", "Failure: Depot Prep should be ACTIVE"
    print("Test 1 Passed: Bottom-up propagation set parent to ACTIVE.")
    
    # Test 2: Complete the free pool
    log_event("TICK", "inspect_frame", "ai_agent_1")
    evaluate_node(DAG)
    assert DAG["children"][0]["status"] == "GREEN", "Failure: Depot Prep should be GREEN"
    print("Test 2 Passed: Completing all children sets parent to GREEN.")
    
    # Test 3: Complete linear chain
    log_event("TICK", "fuel_prime", "human_operator_1")
    log_event("TICK", "ignition", "hardware_sensor_1")
    evaluate_node(DAG)
    assert DAG["children"][1]["status"] == "GREEN", "Failure: Engine Runup should be GREEN"
    print("Test 3 Passed: Engine sequence resolved to GREEN.")
    
    print("\n\033[1m=== FINAL MATERIALIZED STATE ===\033[0m")
    render_tree(DAG)
    print("\n")

if __name__ == "__main__":
    run_self_test()
