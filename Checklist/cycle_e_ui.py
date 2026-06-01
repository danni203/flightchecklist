# cycle_e_ui.py
import datetime
import math

# --- 1. MOCK DATA (Inherited from Cycle C/D Evaluator) ---
# We simulate a mid-operation state: Depot is done, Engine is Active, GPS TTL is ticking.
DAG_STATE = {
    "node_id": "flight_ops", "name": "Flight Ops", "status": "ACTIVE", "node_type": "root",
    "children": [
        {
            "node_id": "depot_prep", "name": "Depot Preparation", "status": "GREEN", "node_type": "free_pool",
            "children": [
                {"name": "Pack Flight Batteries", "status": "GREEN", "node_type": "leaf"},
                {"name": "Airframe Inspection", "status": "GREEN", "node_type": "leaf"}
            ]
        },
        {
            "node_id": "engine_runup", "name": "Engine Runup Sequence", "status": "ACTIVE", "node_type": "linear_chain",
            "children": [
                {"name": "Prime Fuel Lines", "status": "GREEN", "node_type": "leaf"},
                {"name": "Ignition Test", "status": "UNINITIALIZED", "node_type": "leaf"}
            ]
        },
        {
            "node_id": "pre_flight_barrier", "name": "Launch Sync Barrier", "status": "BLOCKED", "node_type": "barrier",
            "children": [
                {"name": "GPS 3D Fix", "status": "GREEN", "node_type": "leaf", "ttl_minutes": 15, "age_minutes": 13.5}
            ]
        }
    ]
}

MANIFEST = {
    "org": "STONEFLY 🪰", "platform": "Project Icarus ✈️", "safe_lines": 12,
    "themes": {
        "day": {"bg": "\033[47m", "fg": "\033[30m", "GREEN": "\033[32m", "AMBER": "\033[33m", "UNINITIALIZED": "\033[90m"},
        "night": {"bg": "\033[40m", "fg": "\033[37m", "GREEN": "\033[92m", "AMBER": "\033[93m", "UNINITIALIZED": "\033[37m"}
    }
}

# --- 2. HEURISTIC FUNCTIONS ---

def determine_theme():
    """Selects day/night mode based on local hour."""
    current_hour = datetime.datetime.now().hour
    mode = "night" if current_hour >= 18 or current_hour < 6 else "day"
    return mode, MANIFEST["themes"][mode]

def extract_alarms(node, alarms):
    """Scans the DAG for approaching TTL expirations to hoist to the Clock UI."""
    if "ttl_minutes" in node and "age_minutes" in node and node["status"] == "GREEN":
        time_left = node["ttl_minutes"] - node["age_minutes"]
        if time_left < 5.0: # Trigger visual alarm if < 5 mins remain
            alarms.append(f"WARN: {node['name']} expires in {math.ceil(time_left)}m")
    
    for child in node.get("children", []):
        extract_alarms(child, alarms)
    return alarms

def count_lines(node):
    """Calculates vertical screen real estate required by a sub-tree."""
    return 1 + sum(count_lines(c) for c in node.get("children", []))

# --- 3. RENDERING ENGINE ---

def render_ui(dag, manifest):
    mode_name, theme = determine_theme()
    RESET = "\033[0m"
    
    # Apply global background/foreground for the device screen
    print(f"{theme['bg']}{theme['fg']}", end="")
    
    # 1. Header & Clock Bar
    print("=" * 50)
    current_time = datetime.datetime.now().strftime("%H:%M ACST")
    print(f" {manifest['org']} | {manifest['platform']} ".ljust(35) + f"[{current_time}]")
    print(f" MODE: {mode_name.upper()} ".ljust(35) + f"[SYS: NOMINAL]")
    
    # 2. Hoisted Alarms
    alarms = extract_alarms(dag, [])
    if alarms:
        print("-" * 50)
        for alarm in alarms:
            print(f" {theme['AMBER']}⚠️  {alarm}{theme['fg']}")
    print("=" * 50)
    
    # 3. Layout Isolation Heuristic
    # If the total required lines exceed our safe screen limits, we paginate
    # and only expand the currently ACTIVE branch, collapsing the rest.
    total_lines = count_lines(dag)
    collapse_inactive = total_lines > manifest['safe_lines']
    
    def draw_node(node, indent=0, is_active_path=False):
        status = node.get("status", "UNINITIALIZED")
        color = theme.get(status, theme["fg"])
        
        # Status iconography
        icon = "[ ]"
        if status == "GREEN": icon = "[✓]"
        elif status == "ACTIVE": icon = "[-]"
        elif status == "BLOCKED": icon = "[X]"
        
        print(f"{'  ' * indent}{color}{icon} {node['name']}{theme['fg']}")
        
        # Heuristic: Do not draw children if we are conserving lines AND branch is fully Green/Inactive
        is_branch_active = status == "ACTIVE"
        if collapse_inactive and not is_branch_active and indent > 0:
            return
            
        for child in node.get("children", []):
            draw_node(child, indent + 1, is_branch_active)

    draw_node(dag)
    print("=" * 50 + RESET)

if __name__ == "__main__":
    render_ui(DAG_STATE, MANIFEST)
