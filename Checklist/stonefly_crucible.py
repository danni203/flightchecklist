# stonefly_crucible.py
import sqlite3, hashlib, json, socket, threading, sys, uuid, random, time

# =============================================================================
# 1. THE TACTICAL DAG, ROLES & MASSIVE ASSET ROSTER
# =============================================================================
ROLES = {
    "depot_mgr": "DEPOT", "commander": "GCS", "pilot": "GCS", "rem_1": "REMOTE",
    "rem_2": "REMOTE", "driver": "LAUNCH_TEAM", "tech_a": "LABOR", "tech_b": "LABOR",
    "recovery_lead": "RECOVERY"
}

# The 50-Piece UAS Master Tool Kit
TOOL_ROSTER = [
    "1/4-inch Drive Inch-Pound Torque Wrench", "3/8-inch Drive Foot-Pound Torque Wrench",
    "Safety Wire Twister Pliers (6-inch)", "Safety Wire Twister Pliers (9-inch)",
    "Fluke 87V Industrial Multimeter", "Metric Ball-End Hex Key Set",
    "Imperial Ball-End Hex Key Set", "Knipex Cobra Water Pump Pliers",
    "Vise-Grip Locking Pliers (Curved Jaw)", "Vise-Grip Needle Nose Locking Pliers",
    "Wera Kraftform Phillips #2 Screwdriver", "Wera Kraftform Phillips #1 Screwdriver",
    "Wera Kraftform Slotted Screwdriver (5.5mm)", "Wera Kraftform Slotted Screwdriver (3.0mm)",
    "JIS (Japanese Industrial Standard) Screwdriver Set", "Wiha Precision Torx Set (T5-T20)",
    "Wiha Precision Hex Driver Set", "Mitutoyo 6-inch Digital Caliper",
    "Starrett Feeler Gauge Set", "Daniels Mfg (DMC) AF8 Crimp Tool",
    "DMC AFM8 Micro Crimp Tool", "D-Sub Pin Insertion/Extraction Tool Kit",
    "Hakko FX-888D Portable Soldering Station", "Weller Portasol Butane Soldering Iron",
    "Kester 63/37 Rosin Core Solder Spool", "Chemtronics Solder Braid (Desoldering Wick)",
    "IDEAL Stripmaster Wire Strippers", "Knipex Electronic Super Knips (Flush Cutters)",
    "Telescoping Inspection Mirror", "Flexible Magnetic Pick-up Tool",
    "Streamlight ProTac Headlamp", "SureFire Stiletto Pro Flashlight",
    "Snap-on 1/4-inch Drive Ratchet", "Snap-on 1/4-inch Drive Metric Socket Set",
    "Snap-on 1/4-inch Drive Deep Socket Set", "GearWrench Metric Ratcheting Wrench Set",
    "GearWrench Imperial Ratcheting Wrench Set", "Knipex Pliers Wrench (8-inch)",
    "Dead Blow Hammer (16 oz)", "Brass/Nylon Dual-Face Hammer",
    "Loctite 242 (Blue) Threadlocker", "Loctite 262 (Red) Threadlocker",
    "Aviation Snips (Straight Cut)", "DeWalt 20V Max Cordless Drill",
    "Milbar 45W Reversible Safety Wire Pliers", "Kapton Tape Roll (1-inch width)",
    "Tesa Wire Loom Tape (Fleece)", "Rigid Borescope Inspection Camera",
    "X-Acto Precision Knife with #11 Blades", "Peli 1510 Protector Case (Master Housing)"
]

DAG = {
    "node_id": "op_icarus_tactical", "name": "Operation Icarus: Tactical Islanding", "node_type": "root", "children": [
        
        # --- PHASE 1: DEPOT ---
        {"node_id": "phase_1_depot", "name": "Phase 1: Depot Operations", "node_type": "barrier", "children": [
            {"node_id": "tool_packing", "name": "Pack 50-Piece Master Tool Kit", "node_type": "leaf", "duration_min": 5},
            {"node_id": "airframe_manifest", "name": "Airframe Manifest Verified", "node_type": "leaf", "prerequisite": "tool_packing", "duration_min": 10},
            {"node_id": "ups_charge", "name": "All UPS & Jackery Units > 95%", "node_type": "leaf", "duration_min": 5},
            {"node_id": "crypto_sync", "name": "Mesh Crypto Keys Synchronized", "node_type": "leaf", "duration_min": 5}
        ]},

        # --- PHASE 2: LONG RANGE TRANSIT ---
        {"node_id": "phase_2_transit", "name": "Phase 2: Transit & Site Security", "node_type": "barrier", "prerequisite": "phase_1_depot", "children": [
            {"node_id": "convoy_arrive", "name": "Convoy Arrival at Target Site", "node_type": "leaf", "duration_min": 360},
            {"node_id": "arrival_audit", "name": "Zero-Emission Inventory Audit", "node_type": "leaf", "prerequisite": "convoy_arrive", "duration_min": 10},
            {"node_id": "perimeter_sec", "name": "Physical Perimeter Secured", "node_type": "leaf", "prerequisite": "arrival_audit", "duration_min": 15}
        ]},

        # --- PHASE 3: COMMS & GCS ---
        {"node_id": "phase_3_gcs", "name": "Phase 3: Network & GCS Assembly", "node_type": "barrier", "prerequisite": "phase_2_transit", "children": [
            {"node_id": "gen_power", "name": "Primary Generator Stable", "node_type": "leaf", "duration_min": 5},
            {"node_id": "starlink_lock", "name": "Starlink Dish Aligned & Sat Lock", "node_type": "leaf", "prerequisite": "gen_power", "duration_min": 5},
            {"node_id": "tac_rf_mast", "name": "Tactical RF Mast Raised", "node_type": "leaf", "duration_min": 15},
            {"node_id": "gcs_boot", "name": "GCS Clean Boot & UPS > 80%", "node_type": "leaf", "prerequisite": "gen_power", "duration_min": 5},
            {"node_id": "rem_hotspot", "name": "Remote: Telstra LTE / Hotspot Functional", "node_type": "leaf", "duration_min": 5},
            {"node_id": "voice_comms", "name": "Voice Rollcall Across All Nodes", "node_type": "leaf", "prerequisite": "starlink_lock", "duration_min": 3}
        ]},

        # --- PHASE 5: AIRFRAME & AVIONICS ---
        {"node_id": "phase_5_airframe", "name": "Phase 5: Airframe & FCU Initialization", "node_type": "barrier", "prerequisite": "phase_3_gcs", "children": [
            {"node_id": "wing_spars", "name": "Wing Spars Locked & Pinned", "node_type": "leaf", "duration_min": 10},
            {"node_id": "load_bats", "name": "Load Flight Batteries & Secure Hatches", "node_type": "leaf", "duration_min": 5},
            {"node_id": "fcu_power", "name": "Apply Power to Flight Control Unit", "node_type": "leaf", "prerequisite": "load_bats", "duration_min": 1},
            {"node_id": "telemetry_link", "name": "GCS MAVLink Heartbeat Established", "node_type": "leaf", "prerequisite": "fcu_power", "duration_min": 2},
            {"node_id": "rc_link", "name": "RC Radio Live & Failsafe Verified", "node_type": "leaf", "prerequisite": "telemetry_link", "duration_min": 2},
            {"node_id": "gps_3d_fix", "name": "GPS 3D Fix & EKF3 Aligned", "node_type": "leaf", "prerequisite": "telemetry_link", "duration_min": 5}
        ]},

        # --- PHASE 6: CONTESTED LAUNCH & ISLANDING ---
        {"node_id": "phase_6_launch", "name": "Phase 6: EMCON Launch Execution", "node_type": "barrier", "prerequisite": "phase_5_airframe", "children": [
            {"node_id": "car_rigged", "name": "Launcher Roof Rigging Secure", "node_type": "leaf", "duration_min": 10},
            {"node_id": "release_test", "name": "Pre-Mount Release Mech Test (Dry Fire)", "node_type": "leaf", "prerequisite": "car_rigged", "duration_min": 2},
            {"node_id": "mount_airframe", "name": "Mount Airframe to Car Rails", "node_type": "leaf", "prerequisite": "release_test", "duration_min": 5},
            
            # AUTOMATED INVENTORY GATE: Checks global ledger for all 50 tools
            {"node_id": "flight_line_tool_sweep", "name": "Automated Master Tool Sweep (50/50 Accounted)", "node_type": "inventory_gate", "target_item": "ALL", "max_allowed_out": 0, "prerequisite": "mount_airframe"},
            
            {"node_id": "launch_auth", "name": "Commander Launch Authority", "node_type": "approval", "prerequisite": "flight_line_tool_sweep"},
            
            # THE EMCON LATCH
            {"node_id": "launch_emcon", "name": "ENGAGE EMCON: Tactical Blackout", "node_type": "leaf", "prerequisite": "launch_auth", "duration_min": 1},
            
            # ISLANDED EXECUTION (Launcher Node Only)
            {"node_id": "car_speed", "name": "Car Accelerating to Target V-Speed", "node_type": "leaf", "prerequisite": "launch_emcon", "duration_min": 2},
            {"node_id": "release_mech", "name": "Airframe Release Mechanism Triggered", "node_type": "leaf", "prerequisite": "car_speed", "duration_min": 1},
            {"node_id": "car_rtb", "name": "Car Decelerate & RTB to Perimeter", "node_type": "leaf", "prerequisite": "release_mech", "duration_min": 4},
            
            # MESH RECONCILIATION
            {"node_id": "emcon_drop", "name": "TERMINATE EMCON: Links Restored", "node_type": "leaf", "prerequisite": "car_rtb", "duration_min": 1},
            {"node_id": "climb_out", "name": "Positive Rate of Climb Confirmed via GCS", "node_type": "leaf", "prerequisite": "emcon_drop", "duration_min": 1}
        ]},

        # --- PHASE 7 & 8: RECOVERY & POST-FLIGHT ---
        {"node_id": "phase_7_recovery", "name": "Phase 7: Recovery Sequence", "node_type": "barrier", "prerequisite": "phase_6_launch", "children": [
            {"node_id": "clear_airspace", "name": "Clear Recovery Airspace", "node_type": "leaf", "duration_min": 5},
            {"node_id": "engine_cut", "name": "Engine Cut / Touchdown", "node_type": "leaf", "prerequisite": "clear_airspace", "duration_min": 1},
            {"node_id": "disarm_fcu", "name": "Disarm FCU & Main Power Off", "node_type": "leaf", "prerequisite": "engine_cut", "duration_min": 2}
        ]},
        {"node_id": "phase_8_rtb", "name": "Phase 8: RTB & Depot Inbound", "node_type": "barrier", "prerequisite": "phase_7_recovery", "children": [
            {"node_id": "data_offload", "name": "Raw Data Log Exfiltration", "node_type": "leaf", "duration_min": 20},
            {"node_id": "site_sterile", "name": "Sterilize Site / Leave No Trace", "node_type": "leaf", "prerequisite": "data_offload", "duration_min": 15},
            {"node_id": "convoy_rtb", "name": "Convoy Transit Return to Depot", "node_type": "leaf", "prerequisite": "site_sterile", "duration_min": 360},
            {"node_id": "mission_close", "name": "Commander Mission Closeout", "node_type": "approval", "prerequisite": "convoy_rtb"}
        ]}
    ]
}

TASK_OWNERS = {
    "tool_packing": "depot_mgr", "airframe_manifest": "depot_mgr", "ups_charge": "tech_a", "crypto_sync": "commander",
    "convoy_arrive": "driver", "arrival_audit": "commander", "perimeter_sec": "tech_b",
    "gen_power": "tech_a", "starlink_lock": "commander", "tac_rf_mast": "tech_b", "gcs_boot": "commander", "rem_hotspot": "rem_1", "voice_comms": "commander",
    "wing_spars": "tech_a", "load_bats": "tech_a", "fcu_power": "tech_b", "telemetry_link": "pilot", "rc_link": "pilot", "gps_3d_fix": "pilot",
    "car_rigged": "driver", "release_test": "driver", "mount_airframe": "tech_a", "launch_auth": "commander", 
    "launch_emcon": "commander", "car_speed": "driver", "release_mech": "driver", "car_rtb": "driver", "emcon_drop": "driver", "climb_out": "pilot",
    "clear_airspace": "recovery_lead", "engine_cut": "pilot", "disarm_fcu": "recovery_lead", "data_offload": "commander", "site_sterile": "recovery_lead", "convoy_rtb": "driver", "mission_close": "commander"
}

# =============================================================================
# 2. VIRTUAL TIME & BAUD-RATE PHYSICS
# =============================================================================
class GlobalClock:
    def __init__(self, time_scale_factor=100.0):
        self.start_real = time.time()
        self.scale = time_scale_factor
        self.lock = threading.Lock()
    def now(self):
        with self.lock: return (time.time() - self.start_real) * self.scale

V_CLOCK = GlobalClock(time_scale_factor=150.0)

class RFNetworkPhysics:
    def __init__(self):
        self.links = {
            "STARLINK": {"bps": 5000000, "base_lat": 0.1}, 
            "TAC_RF": {"bps": 32000, "base_lat": 0.02},    
            "UMBILICAL": {"bps": 100000000, "base_lat": 0.001} 
        }
        self.topology = {} 
        self.jammed_links = set()
        self.lock = threading.Lock()
        
    def set_route(self, n1, n2, link_type):
        with self.lock:
            self.topology[f"{n1}-{n2}"] = link_type
            self.topology[f"{n2}-{n1}"] = link_type

    def is_jammed(self, n1, n2):
        with self.lock: return f"{n1}-{n2}" in self.jammed_links

    def dispatch(self, payload, origin, target, target_port):
        link_type = self.topology.get(f"{origin}-{target}")
        if not link_type or self.is_jammed(origin, target): return 
        
        packet_size_bytes = len(json.dumps(payload).encode('utf-8'))
        link_specs = self.links[link_type]
        transit_time_v_sec = (packet_size_bytes / link_specs["bps"]) + link_specs["base_lat"]
        
        def flight_envelope():
            real_sleep = transit_time_v_sec / V_CLOCK.scale
            time.sleep(real_sleep)
            try:
                if not self.is_jammed(origin, target):
                    s = socket.create_connection(("127.0.0.1", target_port), timeout=0.5)
                    s.sendall((json.dumps(payload) + "\n").encode('utf-8'))
                    s.close()
            except: pass

        threading.Thread(target=flight_envelope, daemon=True).start()

PHYSICS_NET = RFNetworkPhysics()
PHYSICS_NET.set_route("GCS", "REM_1", "STARLINK")
PHYSICS_NET.set_route("GCS", "REM_2", "STARLINK")
PHYSICS_NET.set_route("GCS", "LAUNCHER", "TAC_RF")
PHYSICS_NET.set_route("GCS", "RECOVERY", "TAC_RF")
PHYSICS_NET.set_route("GCS", "LABOR_A", "TAC_RF")
PHYSICS_NET.set_route("GCS", "LABOR_B", "TAC_RF")
PHYSICS_NET.set_route("GCS", "DEPOT", "STARLINK") 

# =============================================================================
# 3. THE STONEFLY DISTRIBUTED ENGINE (Virtual Time Aware)
# =============================================================================
class NodeDaemon:
    def __init__(self, node_id, port, is_hub=False):
        self.node_id = node_id
        self.port = port
        self.is_hub = is_hub
        self.current_session = "UNINITIALIZED" if not is_hub else "CRUCIBLE_OP_04"
        self.peers = {} 
        
        self.db_lock = threading.Lock()
        
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.conn:
            self.conn.execute("PRAGMA journal_mode=WAL;")
            
            self.conn.executescript('''
                CREATE TABLE event_ledger (event_id TEXT PRIMARY KEY, session_uuid TEXT, node_id TEXT, local_seq INTEGER, lamport INTEGER, v_time REAL, action TEXT, target_id TEXT, actor_id TEXT, payload TEXT);
                CREATE TABLE vector_clocks (remote_node TEXT PRIMARY KEY, highest_seq INTEGER);
            ''')
        self.lamport, self.seq = 0, 0
        
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", self.port))
        self.srv.listen(50)
        threading.Thread(target=self._net_listener, daemon=True).start()

    def register_peer(self, peer_id, port): self.peers[peer_id] = port

    def log_event(self, action, target, actor, payload="{}"):
        if self.current_session == "UNINITIALIZED": return
        
        def _write(act, tgt, actr, pay):
            with self.db_lock:
              self.lamport += 1
              self.seq += 1
              ev_id = hashlib.sha256(f"{self.node_id}:{self.seq}".encode()).hexdigest()[:12]
              with self.conn:
                 self.conn.execute("INSERT INTO event_ledger VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (ev_id, self.current_session, self.node_id, self.seq, self.lamport, V_CLOCK.now(), act, tgt, actr, pay))

        _write(action, target, actor, payload)
        
        # Massive Seed: Pack 50 discrete tools into the ledger when packing is ticked
        if target == "tool_packing" and action == "TICK":
            for tool in TOOL_ROSTER:
                _write("ADD_STOCK", tool, "system", '{"qty": 1}')

    def get_vc(self):
        cur = self.conn.cursor()
        cur.execute("SELECT remote_node, highest_seq FROM vector_clocks")
        vc = {r['remote_node']: r['highest_seq'] for r in cur.fetchall()}
        vc[self.node_id] = self.seq
        return vc

    def extract_deltas(self, remote_vc):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM event_ledger ORDER BY lamport ASC")
        return [dict(e) for e in cur.fetchall() if e['node_id'] not in remote_vc or e['local_seq'] > remote_vc.get(e['node_id'], -1)]

    def ingest_deltas(self, deltas):
        with self.db_lock:
           with self.conn:
              for ev in deltas:
                  if self.current_session == "UNINITIALIZED": self.current_session = ev['session_uuid']
                  if ev['session_uuid'] != self.current_session: continue
                  cur = self.conn.execute("INSERT OR IGNORE INTO event_ledger VALUES (:event_id, :session_uuid, :node_id, :local_seq, :lamport, :v_time, :action, :target_id, :actor_id, :payload)", ev)
                  if cur.rowcount > 0:
                      self.lamport = max(self.lamport, ev['lamport']) + 1
                      self.conn.execute("INSERT INTO vector_clocks VALUES (?, ?) ON CONFLICT(remote_node) DO UPDATE SET highest_seq=excluded.highest_seq WHERE excluded.highest_seq>vector_clocks.highest_seq", (ev['node_id'], ev['local_seq']))

    def trigger_gossip(self, peer_id):
        if peer_id not in self.peers: return
        payload = {"type": "HELLO", "origin_id": self.node_id, "vc": self.get_vc()}
        PHYSICS_NET.dispatch(payload, self.node_id, peer_id, self.peers[peer_id])

    def _net_listener(self):
        while True:
            try:
                conn, _ = self.srv.accept()
                msg = None
                buffer = conn.recv(65536).decode('utf-8')
                if "\n" in buffer: msg = json.loads(buffer.split("\n", 1)[0])
                conn.close()
                
                if msg:
                    m_type = msg.get("type")
                    if m_type == "HELLO":
                        reply = {"type": "SYNC_REPLY", "origin_id": self.node_id, "deltas": self.extract_deltas(msg["vc"]), "vc": self.get_vc()}
                        PHYSICS_NET.dispatch(reply, self.node_id, msg["origin_id"], self.peers[msg["origin_id"]])
                    elif m_type == "SYNC_REPLY":
                        self.ingest_deltas(msg["deltas"])
                        ack = {"type": "ACK_FINAL", "origin_id": self.node_id, "deltas": self.extract_deltas(msg["vc"])}
                        PHYSICS_NET.dispatch(ack, self.node_id, msg["origin_id"], self.peers[msg["origin_id"]])
                    elif m_type == "ACK_FINAL":
                        self.ingest_deltas(msg["deltas"])
            except: pass

    def evaluate(self):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM event_ledger WHERE session_uuid=? ORDER BY lamport ASC, node_id ASC, local_seq ASC", (self.current_session,))
        ledger = [dict(r) for r in cur.fetchall()]
        index, state_map = {}, {}
        def build_idx(n):
            index[n["node_id"]] = n
            for c in n.get("children", []): build_idx(c)
        build_idx(DAG)

        def eval_n(n_id):
            if n_id in state_map: return state_map[n_id]
            node = index[n_id]
            ntype, children = node.get("node_type"), node.get("children", [])
            c_sts = [eval_n(c["node_id"]) for c in children]
            st = "UNINITIALIZED"

            if ntype == "leaf":
                evs = [e for e in ledger if e["target_id"] == n_id]
                lt_ev = max(evs, key=lambda x: x["v_time"], default=None) if evs else None
                if lt_ev and lt_ev["action"] == "FAIL": st = "RED"
                else:
                    ticks = [e for e in evs if e["action"] in ["TICK", "ADD_STOCK"]]
                    if ticks: st = "VERIFIED" if len(set(t["actor_id"] for t in ticks)) >= 2 else "GREEN"
            
            elif ntype == "approval":
                lt_app = next((e for e in reversed(ledger) if e["target_id"] == n_id and e["action"] == "APPROVE"), None)
                st = "GREEN" if lt_app else "STAGED"
                
            elif ntype == "inventory_gate":
                inv_state = self.evaluate_inventory(node.get("target_item"))
                max_allowed_out = node.get("max_allowed_out", 0)
                if inv_state["total_owned"] == 0:
                    st = "UNINITIALIZED"
                elif inv_state["currently_deployed"] > max_allowed_out:
                    st = "BLOCKED"
                else:
                    st = "GREEN"
            else:
                if not children: st = "UNINITIALIZED"
                elif any(s == "RED" for s in c_sts): st = "RED"
                elif any(s == "BLOCKED" for s in c_sts): st = "BLOCKED"
                elif all(s in ["GREEN", "VERIFIED"] for s in c_sts): st = "GREEN"
                elif any(s in ["GREEN", "VERIFIED", "ACTIVE", "STAGED"] for s in c_sts): st = "ACTIVE"

            reqs = node.get("prerequisites", []) + ([node["prerequisite"]] if "prerequisite" in node else [])
            if any(eval_n(r) not in ["GREEN", "VERIFIED"] for r in reqs):
                st = "BLOCKED"
                for c in children:
                    def cascade(cn):
                        state_map[cn] = "BLOCKED"
                        index[cn]["status"] = "BLOCKED"
                        for cc in index[cn].get("children", []): cascade(cc["node_id"])
                    cascade(c["node_id"])

            state_map[n_id] = st
            node["status"] = st
            return st
        
        eval_n(DAG["node_id"])
        return state_map

    def evaluate_inventory(self, target_item):
        cur = self.conn.cursor()
        if target_item == "ALL":
            cur.execute("SELECT target_id, action, payload FROM event_ledger WHERE action IN ('ADD_STOCK', 'CHECK_OUT', 'CHECK_IN') ORDER BY lamport ASC")
        else:
            cur.execute("SELECT target_id, action, payload FROM event_ledger WHERE target_id=? AND action IN ('ADD_STOCK', 'CHECK_OUT', 'CHECK_IN') ORDER BY lamport ASC", (target_item,))
        events = cur.fetchall()
        
        inventory_map = {}
        
        for ev in events:
            tid = ev["target_id"]
            if tid not in inventory_map: inventory_map[tid] = {"owned": 0, "out": 0}
            try: data = json.loads(ev["payload"])
            except: data = {}
            qty = data.get("qty", 1)
            
            if ev["action"] == "ADD_STOCK":
                inventory_map[tid]["owned"] += qty
            elif ev["action"] == "CHECK_OUT":
                inventory_map[tid]["out"] += qty
            elif ev["action"] == "CHECK_IN":
                inventory_map[tid]["out"] = max(0, inventory_map[tid]["out"] - qty)

        total_owned = sum(i["owned"] for i in inventory_map.values())
        total_out = sum(i["out"] for i in inventory_map.values())

        return {"total_owned": total_owned, "currently_deployed": total_out}

# =============================================================================
# 4. AUTONOMOUS CREW AI, HOSTILE ADVERSARY & EMCON ENFORCER
# =============================================================================
class AutonomousCrewMember:
    def __init__(self, name, role, node_ref):
        self.name = name
        self.role = role
        self.node = node_ref
        self.running = True
        self.busy_until_vtime = 0.0
        threading.Thread(target=self.work_loop, daemon=True).start()
        threading.Thread(target=self.active_tool_usage_loop, daemon=True).start()
        threading.Thread(target=self.ad_hoc_inventory_loop, daemon=True).start()

    def work_loop(self):
        while self.running:
            v_now = V_CLOCK.now()
            if v_now < self.busy_until_vtime:
                time.sleep(0.1)
                continue
            
            local_state = self.node.evaluate()
            action_taken = False
            for task_id, owner in TASK_OWNERS.items():
                if owner == self.name:
                    status = local_state.get(task_id)
                    if status in ["UNINITIALIZED", "ACTIVE", "STAGED"]:
                        def find_node(n, tid):
                            if n["node_id"] == tid: return n
                            for c in n.get("children", []):
                                res = find_node(c, tid)
                                if res: return res
                            return None
                        node_def = find_node(DAG, task_id)
                        
                        action = "APPROVE" if node_def.get("node_type") == "approval" else "TICK"
                        duration_v_min = node_def.get("duration_min", 1)
                        
                        self.busy_until_vtime = v_now + (duration_v_min * 60)
                        self.node.log_event(action, task_id, self.name)
                        print(f"[{v_now/60:.1f}m] {self.name.upper()} executed [{task_id}] on Node {self.node.node_id}")
                        action_taken = True
                        break 
            
            if not action_taken:
                for peer in self.node.peers.keys(): self.node.trigger_gossip(peer)
            time.sleep(0.2)

    def active_tool_usage_loop(self):
        if self.role not in ["LABOR", "LAUNCH_TEAM"]: return
        while self.running:
            time.sleep(random.uniform(5, 12)) 
            local_state = self.node.evaluate()
            
            # Stop pulling tools when the operation enters Launch Phase to allow the sweep gate to clear
            if local_state.get("phase_6_launch") not in ["UNINITIALIZED", "BLOCKED"]:
                time.sleep(1)
                continue

            if local_state.get("convoy_arrive") not in ["GREEN", "VERIFIED"]:
                continue

            v_now = V_CLOCK.now() / 60.0
            tool_id = random.choice(TOOL_ROSTER)
            
            # Checkout
            self.node.log_event("CHECK_OUT", tool_id, self.name, '{"qty": 1}')
            print(f"\033[93m[{v_now:.1f}m] [TOOL OUT] {self.name.upper()} pulled {tool_id} for flight-line prep.\033[0m")
            
            time.sleep(random.uniform(1, 4))
            
            # Check In
            v_now = V_CLOCK.now() / 60.0
            self.node.log_event("CHECK_IN", tool_id, self.name, '{"qty": 1}')
            print(f"\033[32m[{v_now:.1f}m] [TOOL IN] {self.name.upper()} returned {tool_id} to shadow board.\033[0m")


    def ad_hoc_inventory_loop(self):
        while self.running:
            time.sleep(random.uniform(8, 16)) 
            v_now = V_CLOCK.now() / 60.0
            
            # Query a specific, randomized tool from the roster
            target_tool = random.choice(TOOL_ROSTER)
            inv = self.node.evaluate_inventory(target_tool)
            
            if inv["total_owned"] > 0:
                print(f"\n\033[94m[{v_now:.1f}m] [AD-HOC AUDIT] {self.name.upper()} queried ledger for '{target_tool}' -> Owned: {inv['total_owned']} | Deployed: {inv['currently_deployed']}\033[0m\n")

class HostileAdversary:
    def __init__(self):
        self.running = True
        threading.Thread(target=self.chaos_loop, daemon=True).start()

    def chaos_loop(self):
        while self.running:
            v_now = V_CLOCK.now() / 60.0
            if int(v_now) % 60 == 0 and int(v_now) > 0: 
                print(f"\n\033[91m[!] ADVERSARY: Starlink Terminal UDP Flood. High packet loss induced.\033[0m")
            time.sleep(1) 

class EmconEnforcer:
    def __init__(self, gcs_node, launcher_node):
        self.gcs = gcs_node
        self.launcher = launcher_node
        self.running = True
        self.is_islanded = False
        threading.Thread(target=self.enforce_loop, daemon=True).start()

    def enforce_loop(self):
        while self.running:
            v_now = V_CLOCK.now() / 60.0
            launcher_state = self.launcher.evaluate()
            
            emcon_engaged = launcher_state.get("launch_emcon") in ["GREEN", "VERIFIED"]
            emcon_dropped = launcher_state.get("emcon_drop") in ["GREEN", "VERIFIED"]

            if emcon_engaged and not emcon_dropped and not self.is_islanded:
                self.is_islanded = True
                print(f"\n\033[90m[{v_now:.1f}m] [EMCON LATCH ENGAGED] Tactics Dictate Radio Silence. LAUNCHER node is now islanded.\033[0m")
                PHYSICS_NET.lock.acquire()
                PHYSICS_NET.jammed_links.add("GCS-LAUNCHER")
                PHYSICS_NET.jammed_links.add("LAUNCHER-GCS")
                PHYSICS_NET.lock.release()

            elif emcon_dropped and self.is_islanded:
                self.is_islanded = False
                print(f"\n\033[96m[{v_now:.1f}m] [EMCON LATCH RELEASED] Car RTB complete. Re-establishing link & dumping vector clocks...\033[0m")
                PHYSICS_NET.lock.acquire()
                PHYSICS_NET.jammed_links.discard("GCS-LAUNCHER")
                PHYSICS_NET.jammed_links.discard("LAUNCHER-GCS")
                PHYSICS_NET.lock.release()
            
            time.sleep(0.5)

# =============================================================================
# 5. ORCHESTRATOR 
# =============================================================================
def run_crucible():
    print("="*70)
    print(" STONEFLY OP ALPHA CRUCIBLE | 100x ACCELERATED VIRTUAL TIME")
    print("="*70)
    print("Initializing Geographically Dispersed SQLite Nodes...")
    
    nodes = {
        "GCS": NodeDaemon("GCS", 7001, is_hub=True),
        "REM_1": NodeDaemon("REM_1", 7002),
        "REM_2": NodeDaemon("REM_2", 7003),
        "LAUNCHER": NodeDaemon("LAUNCHER", 7004),
        "RECOVERY": NodeDaemon("RECOVERY", 7005),
        "LABOR_A": NodeDaemon("LABOR_A", 7006),
        "LABOR_B": NodeDaemon("LABOR_B", 7007),
        "DEPOT": NodeDaemon("DEPOT", 7008)
    }

    for n1 in nodes.values():
        for n2 in nodes.values():
            if n1 != n2: n1.register_peer(n2.node_id, n2.port)

    print("Spawning Autonomous Crew AI Threads...")
    crew = [
        AutonomousCrewMember("commander", "GCS", nodes["GCS"]),
        AutonomousCrewMember("pilot", "GCS", nodes["GCS"]),
        AutonomousCrewMember("rem_1", "REMOTE", nodes["REM_1"]),
        AutonomousCrewMember("rem_2", "REMOTE", nodes["REM_2"]),
        AutonomousCrewMember("driver", "LAUNCH_TEAM", nodes["LAUNCHER"]),
        AutonomousCrewMember("tech_a", "LABOR", nodes["LABOR_A"]),
        AutonomousCrewMember("tech_b", "LABOR", nodes["LABOR_B"]),
        AutonomousCrewMember("recovery_lead", "RECOVERY", nodes["RECOVERY"]),
        AutonomousCrewMember("depot_mgr", "DEPOT", nodes["DEPOT"])
    ]

    print("Awakening Hostile Environment Adversary Engine...")
    adversary = HostileAdversary()
    
    print("Engaging Deterministic EMCON Enforcer...")
    emcon_watchdog = EmconEnforcer(nodes["GCS"], nodes["LAUNCHER"])

    print("\n\033[96mOPERATION ICARUS TACTICAL COMMENCING...\033[0m\n")
    
    start_real = time.time()
    root_id = DAG["node_id"]
    
    try:
        while True:
            time.sleep(2) 
            v_now = V_CLOCK.now() / 60.0
            
            gcs_state = nodes["GCS"].evaluate()
            root_status = gcs_state.get(root_id)
            
            print(f"--- V-Time: T+{v_now:.1f} minutes | GCS Master State: {root_status} ---")
            
            if root_status == "GREEN":
                print(f"\n\033[92m[✓] OPERATION COMPLETE. All ledgers validated and closed.\033[0m")
                break
                
            # Watchdog timeout: 10 real minutes allows for heavy virtual timelines
            if (time.time() - start_real) > 600: 
                print("\n\033[91m[X] SIMULATION TIMEOUT. Operational Deadlock.\033[0m")
                break
    except KeyboardInterrupt:
        print("\nAborted.")

    for c in crew: c.running = False
    adversary.running = False
    emcon_watchdog.running = False

if __name__ == "__main__":
    run_crucible()
