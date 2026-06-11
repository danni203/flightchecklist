# stonefly_node.py
import sqlite3, time, hashlib, json, socket, threading, argparse, sys, uuid
from zeroconf import Zeroconf, ServiceInfo, ServiceBrowser, ServiceListener
def get_local_ip():
    """Bypasses localhost to find the machine's actual LAN IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

# mDNS Listener Class ---
class PeerDiscoveryListener(ServiceListener):
    def __init__(self, daemon):
        self.daemon = daemon

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        # Ignore our own broadcast
        if info and not name.startswith(self.daemon.node_id):
            ip = socket.inet_ntoa(info.addresses[0])
            props = {k.decode(): v.decode() for k, v in info.properties.items()}
            
            peer_id = props.get("node_id", "UNKNOWN")
            gossip_port = int(props.get("gossip_port", info.port))

            # Register the discovered peer in the daemon's memory
            self.daemon.peers_registry[peer_id] = {"ip": ip, "port": gossip_port}
            
            # Print a green alert to the terminal without breaking the TUI
            sys.stdout.write(f"\n\033[92m[mDNS] Discovered Active Node: {peer_id} at {ip}:{gossip_port}\033[0m\n")
            sys.stdout.write(f"[{self.daemon.ipc_port}] Command: ")
            sys.stdout.flush()

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None: pass
    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None: pass
# --- 1. CONFIGURATION & ROLES ---
# --- 1. CONFIGURATION & ROLES ---
# Map the PKI Badges to the internal evaluation logic
ROLES = {"OP-JAVAAN-01": "COMMANDER", "TECH-ALPHA": "OPERATOR", "PILOT-BRAVO": "PILOT"}
MANIFEST = {
    "org": "STONEFLY 🪰", "platform": "Project Icarus ✈️",
    "themes": {"night": {"bg": "\033[40m", "fg": "\033[37m", "GREEN": "\033[92m", "VERIFIED": "\033[96m", "AMBER": "\033[93m", "RED": "\033[91m", "OUT": "\033[90m", "STAGED": "\033[95m", "BLOCKED": "\033[31m"}}
}
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
        
        # --- PHASE 4: PRE-FLIGHT BRIEFING ---
        {"node_id": "phase_4_brief", "name": "Phase 4: Commander Go/No-Go", "node_type": "barrier", "prerequisite": "phase_3_gcs", "children": [
            {"node_id": "weather_check", "name": "METAR & Wind Profile Acceptable", "node_type": "leaf", "duration_min": 2},
            {"node_id": "brief_crew", "name": "All Stations Ready Rollcall", "node_type": "leaf", "prerequisite": "weather_check", "duration_min": 3}
        ]},

        # --- PHASE 5: AIRFRAME & AVIONICS ---
        {"node_id": "phase_5_airframe", "name": "Phase 5: Airframe & FCU Initialization", "node_type": "barrier", "prerequisite": "phase_4_brief", "children": [
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
            
            # AUTOMATED INVENTORY GATE: Checks global ledger for tools
            {"node_id": "flight_line_tool_sweep", "name": "Automated Master Tool Sweep (Accounted)", "node_type": "inventory_gate", "target_item": "ALL", "max_allowed_out": 0, "prerequisite": "mount_airframe"},
            
            {"node_id": "launch_auth", "name": "Commander Launch Authority", "node_type": "approval", "prerequisite": "flight_line_tool_sweep"},
            {"node_id": "launch_emcon", "name": "ENGAGE EMCON: Tactical Blackout", "node_type": "leaf", "prerequisite": "launch_auth", "duration_min": 1},
            {"node_id": "car_speed", "name": "Car Accelerating to Target V-Speed", "node_type": "leaf", "prerequisite": "launch_emcon", "duration_min": 2},
            {"node_id": "release_mech", "name": "Airframe Release Mechanism Triggered", "node_type": "leaf", "prerequisite": "car_speed", "duration_min": 1},
            {"node_id": "car_rtb", "name": "Car Decelerate & RTB to Perimeter", "node_type": "leaf", "prerequisite": "release_mech", "duration_min": 4},
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
# --- 2. NETWORK PROTOCOL UTILITIES ---
def send_msg(sock, data):
    sock.sendall((json.dumps(data) + "\n").encode('utf-8'))

def recv_msg(sock):
    buffer = ""
    while True:
        try:
            chunk = sock.recv(4096).decode('utf-8')
            if not chunk: return None
            buffer += chunk
            if "\n" in buffer:
                msg, _ = buffer.split("\n", 1)
                return json.loads(msg)
        except: return None

# --- 3. THE LIVE REFRESH ASYNCHRONOUS TUI ---
class LiveTUI:
    def __init__(self, node_id, ipc_port):
        self.node_id = node_id
        self.ipc_port = ipc_port
        self.running = True
        self.current_response = {"session": "INITIALIZING", "dag": DAG}
        
        # Dedicated thread to constantly pull the absolute ground-truth state from local daemon
        threading.Thread(target=self._update_loop, daemon=True).start()

    def _update_loop(self):
        while self.running:
            try:
                s = socket.create_connection(("127.0.0.1", self.ipc_port), timeout=0.5)
                send_msg(s, {"action": "STATE"})
                res = recv_msg(s)
                s.close()
                if res and res != self.current_response:
                    self.current_response = res
                    self.render()
            except:
                pass
            time.sleep(0.2) # 5Hz refresh check

    def render(self):
        theme = MANIFEST["themes"]["night"]
        # VT100 Escape sequence: Clear screen and park cursor at 0,0
        # Leaving the bottom open for the command entry prompt line
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.write(f"{theme['bg']}{theme['fg']}=== Node: {self.node_id} | Session: {self.current_response['session']} ===\n")
        
        def draw(node, indent=0):
            st = node.get("status", "UNINITIALIZED")
            color = theme.get(st.replace("_OVR", ""), theme["fg"])
            icon = {"GREEN": "[✓]", "VERIFIED": "[V]", "OUT": "[-]", "RED": "[X]", "AMBER": "[!]", "BLOCKED": "[X]", "STAGED": "[?]", "ACTIVE": "[-]", "GREEN_OVR": "[O]"}.get(st, "[ ]")
            sys.stdout.write(f"{'  '*indent}{color}{icon} {node['name']}{theme['fg']}\n")
            for c in node.get("children", []): draw(c, indent+1)

        draw(self.current_response['dag'])
        sys.stdout.write("=" * 55 + "\033[0m\n")
        sys.stdout.write(f"[{self.ipc_port}] Command: ")
        sys.stdout.flush()

# --- 4. ENGINE & GOSSIP SERVER CORE ---
class StoneflyDaemon:
    def __init__(self, node_id, ipc_port, gossip_port, db_path=":memory:"):
        self.node_id = node_id
        self.ipc_port = ipc_port
        self.gossip_port = gossip_port
        self.current_session = "UNINITIALIZED_SESSION"
        
        # Initialize Peer Registry and mDNS Broadcaster ---
        self.peers_registry = {} 
        self.zeroconf = Zeroconf()
        self.local_ip = get_local_ip()

        # Package our node info into the mDNS broadcast properties
        desc = {"node_id": self.node_id, "gossip_port": str(self.gossip_port)}
        self.service_info = ServiceInfo(
            "_stonefly._tcp.local.",
            f"{self.node_id}._stonefly._tcp.local.",
            addresses=[socket.inet_aton(self.local_ip)],
            port=self.gossip_port,
            properties=desc,
            server=f"{self.node_id.lower()}.local."
        )
        # Start broadcasting
        self.zeroconf.register_service(self.service_info)
        # Start listening for others
        self.browser = ServiceBrowser(self.zeroconf, "_stonefly._tcp.local.", PeerDiscoveryListener(self))
        
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.conn:
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.executescript('''
                CREATE TABLE IF NOT EXISTS event_ledger (
                    event_id TEXT PRIMARY KEY, session_uuid TEXT, node_id TEXT, local_seq INTEGER, lamport INTEGER,
                    os_time REAL, action TEXT, target_id TEXT, actor_id TEXT, payload TEXT,
                    UNIQUE(node_id, local_seq)
                );
                CREATE TABLE IF NOT EXISTS vector_clocks (remote_node TEXT PRIMARY KEY, highest_seq INTEGER);
            ''')
        self.lamport, self.seq = self._load_state()
        
        threading.Thread(target=self._ipc_listener, daemon=True).start()
        threading.Thread(target=self._gossip_listener, daemon=True).start()
        # Start the active gossip heartbeat
        threading.Thread(target=self._gossip_heartbeat, daemon=True).start()

    def _load_state(self):
        cur = self.conn.cursor()
        cur.execute("SELECT MAX(lamport), MAX(local_seq) FROM event_ledger WHERE node_id=?", (self.node_id,))
        row = cur.fetchone()
        return (row[0] or 0), (row[1] or 0)

    def log_event(self, action, target, actor, payload=""):
        if action == "INIT_SESSION":
            self.current_session = str(uuid.uuid4())[:8].upper()
        
        # Create a helper function so we can rapidly write multiple events
        def _write(act, tgt, actr, pay):
            self.lamport += 1
            self.seq += 1
            ev_id = hashlib.sha256(f"{self.node_id}:{self.seq}".encode()).hexdigest()[:16]
            with self.conn:
                self.conn.execute(
                    "INSERT INTO event_ledger VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (ev_id, self.current_session, self.node_id, self.seq, self.lamport, time.time(), act, tgt, actr, pay)
                )

        # Write the actual human/AI click to the ledger
        _write(action, target, actor, payload)
        
        # --- NEW: Massive Seed Trigger ---
        # When Phase 1 tool packing is completed, mathematically provision all 50 tools
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
        return [dict(e) for e in cur.fetchall() if e['node_id'] not in remote_vc or e['local_seq'] > remote_vc[e['node_id']]]

    def ingest_deltas(self, deltas):
        with self.conn:
            for ev in deltas:
                if self.current_session == "UNINITIALIZED_SESSION" and ev['action'] == "INIT_SESSION":
                    self.current_session = ev['session_uuid']
                
                if ev['session_uuid'] != self.current_session:
                    continue # Ignore legacy session timelines natively
                
                cur = self.conn.execute(
                    "INSERT OR IGNORE INTO event_ledger VALUES (:event_id, :session_uuid, :node_id, :local_seq, :lamport, :os_time, :action, :target_id, :actor_id, :payload)", ev)
                if cur.rowcount > 0:
                    self.lamport = max(self.lamport, ev['lamport']) + 1
                    self.conn.execute("INSERT INTO vector_clocks VALUES (?, ?) ON CONFLICT(remote_node) DO UPDATE SET highest_seq=excluded.highest_seq WHERE excluded.highest_seq>vector_clocks.highest_seq", (ev['node_id'], ev['local_seq']))
    def _gossip_heartbeat(self):
        """Runs in the background, continuously syncing ledgers with known peers."""
        while True:
            # Gossip every 2 seconds
            time.sleep(2.0) 
            
            # Iterate through all peers discovered by mDNS
            # Using list() to avoid dictionary size changed errors during iteration
            for peer_id, info in list(self.peers_registry.items()):
                self.trigger_gossip(info["ip"], info["port"])
    
    def trigger_gossip(self, peer_ip,peer_port):
        try:
            s = socket.create_connection((peer_ip, peer_port), timeout=1)
            send_msg(s, {"type": "HELLO", "vc": self.get_vc()})
            res = recv_msg(s)
            if res and res.get("type") == "SYNC":
                self.ingest_deltas(res["deltas"])
                send_msg(s, {"type": "ACK", "deltas": self.extract_deltas(res["vc"])})
            s.close()
            return True
        except:
            return False

    def _gossip_listener(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", self.gossip_port))#Listen on all interfaces, not just localhost(127.0.0.1)
        srv.listen(5)
        while True:
            try:
                conn, _ = srv.accept()
                msg = recv_msg(conn)
                if msg and msg.get("type") == "HELLO":
                    send_msg(conn, {"type": "SYNC", "vc": self.get_vc(), "deltas": self.extract_deltas(msg["vc"])})
                    ack = recv_msg(conn)
                    if ack and ack.get("type") == "ACK":
                        self.ingest_deltas(ack["deltas"])
                conn.close()
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
                lt_fail = next((e for e in reversed(evs) if e["action"] == "FAIL"), None)
                lt_out = next((e for e in reversed(evs) if e["action"] == "OUT"), None)
                #lt_ovr = next((e for e in reversed(evs) if e["action"] == "OVERRIDE" and ROLES.get(e["actor_id"]) == "COMMANDER"), None)
                lt_ovr = next((e for e in reversed(evs) if e["action"] == "OVERRIDE"), None)
                lt_ev = max([e for e in [lt_fail, lt_out, lt_ovr] if e], key=lambda x: x["os_time"], default=None)
                
                if lt_ev and lt_ev["action"] == "FAIL": 
                	st = "RED"
                	node["last_actor"] = lt_ev["actor_id"]
                
                elif lt_ev and lt_ev["action"] == "OUT": 
                	st = "OUT"
                	node["last_actor"] = lt_ev["actor_id"]
                elif lt_ev and lt_ev["action"] == "OVERRIDE": 
                	st = "GREEN_OVR"
                	node["last_actor"] = lt_ev["actor_id"]
                	
                else:
                    ticks = [e for e in evs if e["action"] in ["TICK", "INIT_SESSION"]]
                    if ticks:
                        st = "VERIFIED" if len(set(t["actor_id"] for t in ticks)) >= 2 else "GREEN"
                        # Grab the actor from the most recent tick
                        node["last_actor"] = ticks[-1]["actor_id"]
            elif ntype == "approval":
                lt_app = next((e for e in reversed(ledger) if e["target_id"] == n_id and e["action"] == "APPROVE"), None)
                #st = "GREEN" if lt_app and ROLES.get(lt_app["actor_id"]) == "COMMANDER" else "STAGED"
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
                elif any(s == "AMBER" for s in c_sts): st = "AMBER"
                elif all(s in ["GREEN", "VERIFIED", "GREEN_OVR", "OUT"] for s in c_sts): st = "GREEN"
                elif any(s in ["GREEN", "VERIFIED", "GREEN_OVR", "ACTIVE", "STAGED"] for s in c_sts): st = "ACTIVE"

            reqs = node.get("prerequisites", []) + ([node["prerequisite"]] if "prerequisite" in node else [])
            if any(eval_n(r) not in ["GREEN", "VERIFIED", "GREEN_OVR", "OUT"] for r in reqs):
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
        return {"session": self.current_session, "dag": DAG}
    def evaluate_inventory(self, target_item):
        """Calculates physical tool assets deployed vs returned."""
        cur = self.conn.cursor()
        if target_item == "ALL":
            cur.execute("SELECT target_id, action, payload FROM event_ledger WHERE action IN ('ADD_STOCK', 'CHECK_OUT', 'CHECK_IN') ORDER BY lamport ASC")
        else:
            cur.execute("SELECT target_id, action, payload FROM event_ledger WHERE target_id=? AND action IN ('ADD_STOCK', 'CHECK_OUT', 'CHECK_IN') ORDER BY lamport ASC",     (target_item,))
        
        inventory_map = {}
        for ev in cur.fetchall():
            tid = ev["target_id"]
            if tid not in inventory_map: inventory_map[tid] = {"owned": 0, "out": 0}
            try: data = json.loads(ev["payload"])
            except: data = {}
            qty = data.get("qty", 1)
            
            if ev["action"] == "ADD_STOCK": inventory_map[tid]["owned"] += qty
            elif ev["action"] == "CHECK_OUT": inventory_map[tid]["out"] += qty
            elif ev["action"] == "CHECK_IN": inventory_map[tid]["out"] = max(0, inventory_map[tid]["out"] - qty)

        total_owned = sum(i["owned"] for i in inventory_map.values())
        total_out = sum(i["out"] for i in inventory_map.values())
        return {"total_owned": total_owned, "currently_deployed": total_out}
    def _ipc_listener(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", self.ipc_port))
        srv.listen(5)
        while True:
            try:
                conn, _ = srv.accept()
                cmd = recv_msg(conn)
                if cmd:
                    action = cmd.get("action")
                    if action in ["TICK", "FAIL", "OUT", "OVERRIDE", "APPROVE", "INIT_SESSION"]:
                        self.log_event(action, cmd["target"], cmd["actor"])
                    elif action == "SYNC":
                        self.trigger_gossip(int(cmd["peer_port"]))
                    send_msg(conn, self.evaluate())
                conn.close()
            except: pass

# --- 5. SYNCHRONOUS COMMAND ENTRY LOOP ---
def run_interactive_client(node_id, ipc_port):
    # Fire up the non-blocking background TUI rendering thread
    LiveTUI(node_id, ipc_port)
    
    # Let the TUI clear the screen and settle its initial render layout
    time.sleep(0.2)
    
    while True:
        try:
            cmd = input().strip().split()
            if not cmd:
                # Force a manual redraw if user presses enter blankly
                sys.stdout.write("\033[F") 
                sys.stdout.flush()
                continue
            
            action = cmd[0].upper()
            if action == "EXIT": break
            
            # Formulate outbound JSON IPC message packet
            payload = {"action": "STATE"}
            if action == "INIT":
                payload = {"action": "INIT_SESSION", "target": "pack_bats", "actor": "javaan"}
            elif action == "SYNC":
                payload = {"action": "SYNC", "peer_port": int(cmd[1])}
            elif action in ["TICK", "FAIL", "OUT", "OVERRIDE", "APPROVE"]:
                payload = {"action": action, "target": cmd[1], "actor": cmd[2]}
            
            # Send payload to local daemon port
            try:
                s = socket.create_connection(("127.0.0.1", ipc_port), timeout=1)
                send_msg(s, payload)
                recv_msg(s) # Flush the daemon's immediate evaluation response
                s.close()
            except Exception as e:
                print(f"\nIPC Error: {e}")
        except KeyboardInterrupt: break

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", default="ALPHA")
    parser.add_argument("--ipc", type=int, default=5001)
    parser.add_argument("--gossip", type=int, default=6001)
    args = parser.parse_args()

    # Automatically boots both backend server engines and interactive client threads simultaneously
    StoneflyDaemon(args.id, args.ipc, args.gossip)
    run_interactive_client(args.id, args.ipc)
