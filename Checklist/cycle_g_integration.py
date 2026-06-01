# cycle_g_integration.py
import sqlite3
import time
import hashlib
from typing import List, Dict

# --- 1. THE TOPOLOGY & RBAC (From Cycle D) ---
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

ROLES = {
    "tech_1": "OPERATOR",
    "hardware_sensor_1": "SYSTEM",
    "javaan": "COMMANDER"
}

# --- 2. DISTRIBUTED LEDGER (From Cycle F, adapted for injected time) ---
class DistributedLedger:
    def __init__(self, db_path: str, node_id: str):
        self.node_id = node_id
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lamport_clock = 0
        self.local_seq = 0
        
        with self.conn:
            self.conn.executescript('''
                CREATE TABLE IF NOT EXISTS event_ledger (
                    event_id TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL,
                    local_seq INTEGER NOT NULL,
                    lamport_clock INTEGER NOT NULL,
                    os_time REAL NOT NULL,
                    action TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    payload TEXT,
                    UNIQUE(node_id, local_seq)
                );
                CREATE TABLE IF NOT EXISTS vector_clocks (
                    remote_node_id TEXT PRIMARY KEY, highest_seq INTEGER NOT NULL
                );
            ''')

    def log_local_event(self, action: str, target_id: str, actor_id: str, payload: str = "", current_os_time: float = 0.0) -> dict:
        self.lamport_clock += 1
        self.local_seq += 1
        event_id = hashlib.sha256(f"{self.node_id}:{self.local_seq}".encode()).hexdigest()[:16]

        event = {
            "event_id": event_id, "node_id": self.node_id, "local_seq": self.local_seq,
            "lamport_clock": self.lamport_clock, "os_time": current_os_time,
            "action": action, "target_id": target_id, "actor_id": actor_id, "payload": payload
        }

        with self.conn:
            self.conn.execute('''
                INSERT INTO event_ledger 
                VALUES (:event_id, :node_id, :local_seq, :lamport_clock, :os_time, :action, :target_id, :actor_id, :payload)
            ''', event)
        return event

    def get_vector_clock(self) -> Dict[str, int]:
        cur = self.conn.cursor()
        cur.execute("SELECT remote_node_id, highest_seq FROM vector_clocks")
        vc = {row['remote_node_id']: row['highest_seq'] for row in cur.fetchall()}
        vc[self.node_id] = self.local_seq
        return vc

    def extract_deltas(self, remote_vc: Dict[str, int]) -> List[dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM event_ledger ORDER BY lamport_clock ASC")
        return [dict(ev) for ev in cur.fetchall() if ev['node_id'] not in remote_vc or ev['local_seq'] > remote_vc[ev['node_id']]]

    def ingest_deltas(self, incoming_events: List[dict]):
        with self.conn:
            for ev in incoming_events:
                cur = self.conn.execute('''
                    INSERT OR IGNORE INTO event_ledger 
                    VALUES (:event_id, :node_id, :local_seq, :lamport_clock, :os_time, :action, :target_id, :actor_id, :payload)
                ''', ev)
                if cur.rowcount > 0:
                    self.lamport_clock = max(self.lamport_clock, ev['lamport_clock']) + 1
                    self.conn.execute('''
                        INSERT INTO vector_clocks (remote_node_id, highest_seq) VALUES (?, ?)
                        ON CONFLICT(remote_node_id) DO UPDATE SET highest_seq = excluded.highest_seq 
                        WHERE excluded.highest_seq > vector_clocks.highest_seq
                    ''', (ev['node_id'], ev['local_seq']))

    def get_ordered_ledger(self) -> List[dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM event_ledger ORDER BY lamport_clock ASC, node_id ASC, local_seq ASC")
        return [dict(row) for row in cur.fetchall()]


# --- 3. THE EVALUATION ENGINE ---
class DAGEvaluator:
    def __init__(self, dag: dict, rbac: dict):
        self.root_dag = dag
        self.rbac = rbac
        self.node_index = {}
        self.state_map = {}
        self.current_ledger = []
        self.current_time = 0.0
        
        self._build_index(self.root_dag)

    def _build_index(self, node):
        self.node_index[node["node_id"]] = node
        for child in node.get("children", []):
            self._build_index(child)

    def _cascade_block(self, node_id):
        node = self.node_index[node_id]
        node["status"] = "BLOCKED"
        self.state_map[node_id] = "BLOCKED"
        for child in node.get("children", []):
            self._cascade_block(child["node_id"])

    def _evaluate_node(self, node_id):
        if node_id in self.state_map:
            return self.state_map[node_id]

        node = self.node_index[node_id]
        node_type = node.get("node_type")
        base_status = "UNINITIALIZED"

        children = node.get("children", [])
        child_statuses = [self._evaluate_node(c["node_id"]) for c in children]

        if node_type == "leaf":
            latest_tick = next((e for e in reversed(self.current_ledger) if e["target_id"] == node_id and e["action"] == "TICK"), None)
            latest_auth_override = next((e for e in reversed(self.current_ledger) if e["target_id"] == node_id and e["action"] == "OVERRIDE" and self.rbac.get(e["actor_id"]) == "COMMANDER"), None)
            
            if latest_auth_override and (not latest_tick or latest_auth_override["os_time"] >= latest_tick["os_time"]):
                base_status = "GREEN_OVR"
            elif latest_tick:
                if "ttl_minutes" in node:
                    age_minutes = (self.current_time - latest_tick["os_time"]) / 60.0
                    base_status = "AMBER" if age_minutes > node["ttl_minutes"] else "GREEN"
                else:
                    base_status = "GREEN"
                    
        elif node_type == "approval":
            latest_approve = next((e for e in reversed(self.current_ledger) if e["target_id"] == node_id and e["action"] == "APPROVE"), None)
            base_status = "GREEN" if latest_approve and self.rbac.get(latest_approve["actor_id"]) == "COMMANDER" else "STAGED"
                
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

        reqs = []
        if "prerequisite" in node: reqs.append(node["prerequisite"])
        if "prerequisites" in node: reqs.extend(node["prerequisites"])

        local_block = False
        for req_id in reqs:
            if self._evaluate_node(req_id) not in ["GREEN", "GREEN_OVR"]:
                local_block = True
                break

        if local_block:
            base_status = "BLOCKED"
            for child in children:
                self._cascade_block(child["node_id"])

        self.state_map[node_id] = base_status
        node["status"] = base_status
        return base_status

    def evaluate_graph(self, ledger: List[dict], current_time: float):
        self.state_map.clear()
        self.current_ledger = ledger
        self.current_time = current_time
        self._evaluate_node(self.root_dag["node_id"])
        return self.root_dag

# --- 4. ASCII RENDERER ---
def render_tree(node, indent=0):
    colors = {
        "UNINITIALIZED": "\033[90m[ ]\033[0m", "ACTIVE": "\033[94m[-]\033[0m", 
        "GREEN": "\033[92m[✓]\033[0m", "GREEN_OVR": "\033[96m[O]\033[0m", 
        "AMBER": "\033[93m[!]\033[0m", "BLOCKED": "\033[91m[X]\033[0m",
        "STAGED": "\033[95m[?]\033[0m"     
    }
    meta = []
    if "ttl_minutes" in node: meta.append(f"TTL:{node['ttl_minutes']}m")
    meta_str = f" \033[90m({', '.join(meta)})\033[0m" if meta else ""
    
    print(f"{'    ' * indent}{colors.get(node.get('status', 'UNINITIALIZED'))} {node['name']}{meta_str}")
    for child in node.get("children", []):
        render_tree(child, indent + 1)


# --- 5. SYSTEM INTEGRATION TEST HARNESS ---
if __name__ == "__main__":
    print("\n\033[1m--- INTEGRATION CYCLE G: DISTRIBUTED LEDGER + DAG EVALUATOR ---\033[0m")
    
    hub_db = DistributedLedger(":memory:", "GCS_Hub")
    tablet_db = DistributedLedger(":memory:", "Android_Tablet_Alpha")
    engine = DAGEvaluator(DAG, ROLES)

    MOCK_TIME = 0.0

    print("1. Tablet operates offline in the depot...")
    tablet_db.log_local_event("TICK", "pack_bats", "tech_1", current_os_time=MOCK_TIME)
    tablet_db.log_local_event("TICK", "inspect_frame", "tech_1", current_os_time=MOCK_TIME)

    print("2. Hub operates offline at the launchpad...")
    hub_db.log_local_event("TICK", "fuel_prime", "tech_1", current_os_time=MOCK_TIME)
    hub_db.log_local_event("TICK", "ignition", "hardware_sensor_1", current_os_time=MOCK_TIME)
    hub_db.log_local_event("TICK", "gps_lock", "hardware_sensor_1", current_os_time=MOCK_TIME)

    print("3. Executing Mesh Sync...")
    hub_vc = hub_db.get_vector_clock()
    tablet_vc = tablet_db.get_vector_clock()
    hub_db.ingest_deltas(tablet_db.extract_deltas(hub_vc))
    tablet_db.ingest_deltas(hub_db.extract_deltas(tablet_vc))

    print("4. Advancing time by 16 minutes (triggering TTL decay)...")
    MOCK_TIME += (16 * 60)

    print("5. Commander issues Override and final Approval on the Hub...")
    hub_db.log_local_event("OVERRIDE", "gps_lock", "javaan", payload="Lock physically verified", current_os_time=MOCK_TIME)
    hub_db.log_local_event("APPROVE", "commander_authority", "javaan", current_os_time=MOCK_TIME)

    print("\n\033[1m=== EVALUATING FINAL STATE MATRIX ===\033[0m")
    ordered_history = hub_db.get_ordered_ledger()
    final_dag = engine.evaluate_graph(ordered_history, MOCK_TIME)
    render_tree(final_dag)
    print("\n")
