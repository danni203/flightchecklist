# cycle_a_core.py

# 1. The Hardcoded Topology (Our Scratch Space)
DAG = {
    "node_id": "flight_ops",
    "name": "Project Icarus Flight Ops",
    "node_type": "root",
    "status": "UNINITIALIZED",
    "children": [
        {
            "node_id": "depot_prep",
            "name": "Depot Preparation",
            "node_type": "free_pool",
            "status": "UNINITIALIZED",
            "children": [
                {"node_id": "pack_bats", "name": "Pack Flight Batteries", "node_type": "leaf", "status": "UNINITIALIZED"},
                {"node_id": "inspect_frame", "name": "Airframe Inspection", "node_type": "leaf", "status": "UNINITIALIZED"}
            ]
        },
        {
            "node_id": "engine_runup",
            "name": "Engine Runup Sequence",
            "node_type": "linear_chain",
            "status": "UNINITIALIZED",
            "children": [
                {"node_id": "fuel_prime", "name": "Prime Fuel Lines", "node_type": "leaf", "status": "UNINITIALIZED"},
                {"node_id": "ignition", "name": "Ignition Test", "node_type": "leaf", "prerequisite": "fuel_prime", "status": "UNINITIALIZED"}
            ]
        },
        {
            "node_id": "pre_flight_barrier",
            "name": "Launch Synchronization Barrier",
            "node_type": "barrier",
            "prerequisites": ["depot_prep", "engine_runup"],
            "status": "UNINITIALIZED",
            "children": [
                {"node_id": "gps_lock", "name": "GPS 3D Fix", "node_type": "leaf", "ttl_minutes": 15, "status": "UNINITIALIZED"}
            ]
        },
        {
            "node_id": "commander_authority",
            "name": "Final Launch Authority",
            "node_type": "approval",
            "prerequisite": "pre_flight_barrier",
            "status": "UNINITIALIZED",
            "children": []
        }
    ]
}

# 2. The ASCII Rendering Engine
def render_tree(node, indent=0, is_last=True):
    """Recursively walks the DAG to project the Traffic Light Array."""
    # ASCII branch formatting
    branch = "└── " if is_last else "├── "
    prefix = "    " * indent + (branch if indent > 0 else "")
    
    # Status color mapping (using basic ANSI terminal colors)
    colors = {
        "UNINITIALIZED": "\033[90m[ ]\033[0m", # Gray
        "ACTIVE": "\033[94m[-]\033[0m",        # Blue
        "GREEN": "\033[92m[✓]\033[0m",         # Green
        "AMBER": "\033[93m[!]\033[0m",         # Yellow
        "RED": "\033[91m[x]\033[0m",           # Red
        "STAGED": "\033[95m[?]\033[0m"         # Magenta (Pending Approval)
    }
    
    status_icon = colors.get(node["status"], "[ ]")
    
    # Render node metadata (TTL, Prerequisites)
    meta = []
    if "ttl_minutes" in node:
        meta.append(f"TTL:{node['ttl_minutes']}m")
    if "prerequisite" in node:
        meta.append(f"Req:{node['prerequisite']}")
    if "prerequisites" in node:
        meta.append(f"Reqs:{','.join(node['prerequisites'])}")
    
    meta_str = f" \033[90m({', '.join(meta)})\033[0m" if meta else ""
    
    # Print the current node
    print(f"{prefix}{status_icon} {node['name']} {meta_str}")
    
    # Recurse through children
    children = node.get("children", [])
    for i, child in enumerate(children):
        render_tree(child, indent + 1, is_last=(i == len(children) - 1))

if __name__ == "__main__":
    print("\n\033[1m=== STONEFLY JINST OPS TERMINAL ===\033[0m")
    render_tree(DAG)
    print("\n")
