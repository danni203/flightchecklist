import sqlite3, time, hashlib, datetime, json
from typing import List, Dict

# --- 1. CONFIGURATION & TOPOLOGY ---
ROLES = {
    "tech_1": "OPERATOR", "tech_2": "OPERATOR", 
    "hardware_1": "SYSTEM", "javaan": "COMMANDER"
}

MANIFEST = {
    "org": "STONEFLY 🪰", "platform": "Project Icarus ✈️", "safe_lines": 30,
    "themes": {
        "night": {
            "bg": "\033[40m", "fg": "\033[37m", 
            "GREEN": "\033[92m", "VERIFIED": "\033[96m", "AMBER": "\033[93m", 
            "RED": "\033[91m", "OUT": "\033[90m", "STAGED": "\033[95m", "BLOCKED": "\033[31m"
        }
    }
}

DAG = {
    "node_id": "mission_lifecycle", "name": "Project Icarus: Full Mission Lifecycle", "node_type": "root",
    "children": [
        {
            "node_id": "phase_1_depot", "name": "Phase 1: Depot Prep", "node_type": "free_pool",
            "children": [
                {"node_id": "pack_bats", "name": "Pack Batteries", "node_type": "leaf"},
                {"node_id": "payload_mod", "name": "Optical Payload", "node_type": "leaf"}
            ]
        },
        {
            "node_id": "phase_2_runup", "name": "Phase 2: Engine Runup", "node_type": "linear_chain",
            "children": [
                {"node_id": "fuel_prime", "name": "Prime Fuel Lines", "node_type": "leaf"},
                {"node_id": "ignition", "name": "Ignition Test", "node_type": "leaf", "prerequisite": "fuel_prime"}
            ]
        },
        {
            "node_id": "phase_3_preflight", "name": "Phase 3: Launch Sync Barrier", "node_type": "barrier",
            "prerequisites": ["phase_1_depot", "phase_2_runup"],
            "children": [
                {"node_id": "gps_lock", "name": "GPS 3D Fix", "node_type": "leaf", "ttl_minutes": 15},
                {"node_id": "crew_brief", "name": "Personnel Array & Brief", "node_type": "leaf"}
            ]
        },
        {
            "node_id": "phase_4_auth", "name": "Phase 4: Launch Authority", "node_type": "approval",
            "prerequisite": "phase_3_preflight"
        },
        {
            "node_id": "phase_5_recovery", "name": "Phase 5: Post-Flight Recovery", "node_type": "linear_chain",
            "prerequisite": "phase_4_auth",
            "children": [
                {"node_id": "touchdown", "name": "Touchdown Confirmed", "node_type": "leaf"},
                {"node_id": "engine_safe", "name": "Engine Safed", "node_type": "leaf", "prerequisite": "touchdown"}
            ]
        },
        {
            "node_id": "phase_6_dismount", "name": "Phase 6: Depot Dismount", "node_type": "barrier",
            "prerequisite": "phase_5_recovery",
            "children": [
                {"node_id": "data_offload", "name": "Payload Data Offload", "node_type": "leaf"},
                {"node_id": "bat_store", "name": "Batteries to Storage", "node_type": "leaf"}
            ]
        }
    ]
}

# --- 2. DISTRIBUTED LEDGER ---
class Ledger:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lamport = 0
        self.seq = 0
        with self.conn:
            self.conn.executescript('''
                CREATE TABLE event_ledger (
                    event_id TEXT PRIMARY KEY, local_seq INTEGER, lamport INTEGER,
                    os_time REAL, action TEXT, target_id TEXT, actor_id TEXT, payload TEXT
                );
            ''')

    def log(self, action: str, target: str, actor: str, os_time: float, payload: str = ""):
        self.lamport += 1
        self.seq += 1
        ev_id = hashlib.sha256(f"local:{self.seq}".encode()).hexdigest()[:16]
        with self.conn:
            self.conn.execute(
                "INSERT INTO event_ledger VALUES (?,?,?,?,?,?,?,?)",
                (ev_id, self.seq, self.lamport, os_time, action, target, actor, payload)
            )

    def get_history(self):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM event_ledger ORDER BY lamport ASC, local_seq ASC")
        return [dict(r) for r in cur.fetchall()]

# --- 3. EVALUATOR ENGINE ---
class Evaluator:
    def __init__(self, dag, rbac):
        self.root = dag
        self.rbac = rbac
        self.index = {}
        self.state_map = {}
        self.ledger = []
        self.time = 0.0
        self._build_idx(self.root)

    def _build_idx(self, node):
        self.index[node["node_id"]] = node
        for c in node.get("children", []): self._build_idx(c)

    def _cascade_block(self, node_id):
        self.state_map[node_id] = "BLOCKED"
        self.index[node_id]["status"] = "BLOCKED"
        for c in self.index[node_id].get("children", []): self._cascade_block(c["node_id"])

    def eval_graph(self, ledger, current_time):
        self.state_map.clear()
        self.ledger = ledger
        self.time = current_time
        self._eval_node(self.root["node_id"])
        return self.root

    def _eval_node(self, node_id):
        if node_id in self.state_map: return self.state_map[node_id]
        node = self.index[node_id]
        ntype = node.get("node_type")
        children = node.get("children", [])
        c_statuses = [self._eval_node(c["node_id"]) for c in children]
        status = "UNINITIALIZED"

        if ntype == "leaf":
            events = [e for e in self.ledger if e["target_id"] == node_id]
            latest_fail = next((e for e in reversed(events) if e["action"] == "FAIL"), None)
            latest_out = next((e for e in reversed(events) if e["action"] == "OUT"), None)
            latest_ovr = next((e for e in reversed(events) if e["action"] == "OVERRIDE" and self.rbac.get(e["actor_id"]) == "COMMANDER"), None)
            
            latest_event = max([e for e in [latest_fail, latest_out, latest_ovr] if e], key=lambda x: x["os_time"], default=None)
            
            if latest_event and latest_event["action"] == "FAIL": status = "RED"
            elif latest_event and latest_event["action"] == "OUT": status = "OUT"
            elif latest_event and latest_event["action"] == "OVERRIDE": status = "GREEN_OVR"
            else:
                ticks = [e for e in events if e["action"] == "TICK"]
                if ticks:
                    ttl = node.get("ttl_minutes", float('inf'))
                    valid_ticks = [t for t in ticks if (self.time - t["os_time"])/60.0 <= ttl]
                    if not valid_ticks: status = "AMBER"
                    else:
                        actors = set(t["actor_id"] for t in valid_ticks)
                        status = "VERIFIED" if len(actors) >= 2 else "GREEN"

        elif ntype == "approval":
            latest_app = next((e for e in reversed(self.ledger) if e["target_id"] == node_id and e["action"] == "APPROVE"), None)
            status = "GREEN" if latest_app and self.rbac.get(latest_app["actor_id"]) == "COMMANDER" else "STAGED"
        else:
            if not children: status = "UNINITIALIZED"
            elif any(s == "RED" for s in c_statuses): status = "RED"
            elif any(s == "BLOCKED" for s in c_statuses): status = "BLOCKED"
            elif any(s == "AMBER" for s in c_statuses): status = "AMBER"
            elif all(s in ["GREEN", "VERIFIED", "GREEN_OVR", "OUT"] for s in c_statuses): status = "GREEN"
            elif any(s in ["GREEN", "VERIFIED", "GREEN_OVR", "ACTIVE", "STAGED"] for s in c_statuses): status = "ACTIVE"

        # Apply Lateral Prerequisites
        reqs = node.get("prerequisites", []) + ([node["prerequisite"]] if "prerequisite" in node else [])
        if any(self._eval_node(r) not in ["GREEN", "VERIFIED", "GREEN_OVR", "OUT"] for r in reqs):
            status = "BLOCKED"
            for c in children: self._cascade_block(c["node_id"])

        self.state_map[node_id] = status
        node["status"] = status
        return status

# --- 4. UI RENDERER & REPL ---
def render(dag, manifest, current_time):
    theme = manifest["themes"]["night"]
    print(f"\033[2J\033[H{theme['bg']}{theme['fg']}", end="") # Clear screen
    print(f"=== {manifest['org']} | {manifest['platform']} ".ljust(45) + f"[{current_time/60:.0f}m] ===")
    
    alarms = []
    def scan_alarms(n):
        if n.get("status") == "RED": alarms.append(f"CRITICAL: {n['name']} FAILED")
        for c in n.get("children", []): scan_alarms(c)
    scan_alarms(dag)
    for a in alarms: print(f" {theme['RED']}⚠️  {a}{theme['fg']}")
    if alarms: print("-" * 55)

    def draw(node, indent=0):
        st = node.get("status", "UNINITIALIZED")
        color = theme.get(st.replace("_OVR", ""), theme["fg"])
        icon = {"GREEN": "[✓]", "VERIFIED": "[V]", "OUT": "[-]", "RED": "[X]", "AMBER": "[!]", "BLOCKED": "[X]", "STAGED": "[?]", "ACTIVE": "[-]", "GREEN_OVR": "[O]"}.get(st, "[ ]")
        
        if st == "OUT": color = theme["OUT"]
        
        meta = []
        if "ttl_minutes" in node: meta.append(f"TTL:{node['ttl_minutes']}m")
        meta_str = f" ({','.join(meta)})" if meta else ""
        
        print(f"{'  '*indent}{color}{icon} {node['name']}{meta_str}{theme['fg']}")
        for c in node.get("children", []): draw(c, indent+1)

    draw(dag)
    print("=" * 55 + "\033[0m\n")

def run_repl():
    ledger = Ledger()
    engine = Evaluator(DAG, ROLES)
    mock_time = 0.0

    print("Commands: tick <node> <actor>, fail <node> <actor>, out <node> <actor>")
    print("          verify <node> <actor2>, time <mins>, override/approve, exit")
    
    while True:
        dag_state = engine.eval_graph(ledger.get_history(), mock_time)
        render(dag_state, MANIFEST, mock_time)
        
        cmd = input("STONEFLY> ").strip().split()
        if not cmd: continue
        action = cmd[0].lower()
        
        if action == "exit": break
        elif action == "time":
            mock_time += float(cmd[1]) * 60
        elif action in ["tick", "fail", "out", "verify"]:
            db_action = "FAIL" if action == "fail" else "OUT" if action == "out" else "TICK"
            ledger.log(db_action, cmd[1], cmd[2], mock_time)
        elif action == "override":
            ledger.log("OVERRIDE", cmd[1], cmd[2], mock_time, payload=" ".join(cmd[3:]))
        elif action == "approve":
            ledger.log("APPROVE", cmd[1], cmd[2], mock_time)

if __name__ == "__main__":
    run_repl()
