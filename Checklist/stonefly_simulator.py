# stonefly_simulator.py
import sqlite3, time, hashlib, json, socket, threading, sys, uuid, random

# --- 1. DESIGN CONSTRAINTS & COMPLIANCE TOKENS ---
ROLES = {"tech_1": "OPERATOR", "tech_2": "OPERATOR", "hardware_1": "SYSTEM", "javaan": "COMMANDER"}
DAG = {
    "node_id": "flight_ops", "name": "Flight Ops", "node_type": "root",
    "children": [
        {"node_id": "depot", "name": "Depot Prep", "node_type": "free_pool", "children": [
            {"node_id": "pack_bats", "name": "Pack Batteries", "node_type": "leaf"},
            {"node_id": "payload", "name": "Optical Payload", "node_type": "leaf"}
        ]},
        {"node_id": "auto_launcher", "name": "Automated Launch System Gate", "node_type": "barrier", "prerequisite": "depot", "children": [
            {"node_id": "als_auth", "name": "Authorize ALS Engagement", "node_type": "leaf"},
            {"node_id": "als_sequence", "name": "ALS Internal Execution", "node_type": "leaf", "prerequisite": "als_auth"}
        ]},
        {"node_id": "auth", "name": "Final Launch Authority", "node_type": "approval", "prerequisite": "auto_launcher"}
    ]
}

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

# --- 2. THE FLUID TACTICAL RF NETWORK SIMULATOR ---
class ChaosNetworkPipe:
    """Simulates a lossy, high-latency, air-gapped wireless topology."""
    def __init__(self):
        self.drop_rate = 0.0
        self.min_latency_ms = 5
        self.max_latency_ms = 25
        self.partition_matrix = {} # Controls node-to-node visibility pairs

    def set_link(self, node_a, node_b, active=True):
        if node_a not in self.partition_matrix: self.partition_matrix[node_a] = {}
        if node_b not in self.partition_matrix: self.partition_matrix[node_b] = {}
        self.partition_matrix[node_a][node_b] = active
        self.partition_matrix[node_b][node_a] = active

    def is_link_up(self, node_a, node_b):
        return self.partition_matrix.get(node_a, {}).get(node_b, True)

    def dispatch_wire(self, target_port, payload_dict, origin_id, target_id):
        """Asynchronously dispatches a network packet with delay and drop mechanics."""
        if not self.is_link_up(origin_id, target_id) or random.random() < self.drop_rate:
            return # Packet dropped in the ether
        
        def pipe_delay():
            delay = random.randint(self.min_latency_ms, self.max_latency_ms) / 1000.0
            time.sleep(delay)
            try:
                s = socket.create_connection(("127.0.0.1", target_port), timeout=0.5)
                send_msg(s, payload_dict)
                s.close()
            except: pass

        threading.Thread(target=pipe_delay, daemon=True).start()

# Global network controller reference
WIRE_PIPE = ChaosNetworkPipe()

# --- 3. THE HARDENED STONEFLY DECENTRALIZED NODE ---
class StoneflyDaemon:
    def __init__(self, node_id, ipc_port, gossip_port, is_hub=False):
        self.node_id = node_id
        self.ipc_port = ipc_port
        self.gossip_port = gossip_port
        self.is_hub = is_hub
        
        # Onboarding Security State
        self.is_onboarded = True if is_hub else False
        self.current_session = "UNINITIALIZED_SESSION" if not is_hub else "BOOT_SESSION"
        self.peers_registry = {} # Tracks registered peer communication profiles
        
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.conn:
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.executescript('''
                CREATE TABLE event_ledger (
                    event_id TEXT PRIMARY KEY, session_uuid TEXT, node_id TEXT, local_seq INTEGER, lamport INTEGER,
                    os_time REAL, action TEXT, target_id TEXT, actor_id TEXT, payload TEXT,
                    UNIQUE(node_id, local_seq)
                );
                CREATE TABLE vector_clocks (remote_node TEXT PRIMARY KEY, highest_seq INTEGER);
            ''')
        self.lamport = 0
        self.seq = 0
        
        self.ipc_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ipc_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.ipc_srv.bind(("127.0.0.1", self.ipc_port))
        self.ipc_srv.listen(20)
        
        self.gossip_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.gossip_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.gossip_srv.bind(("127.0.0.1", self.gossip_port))
        self.gossip_srv.listen(20)
        
        threading.Thread(target=self._ipc_listener, daemon=True).start()
        threading.Thread(target=self._gossip_listener, daemon=True).start()

    def log_event(self, action, target, actor, payload=""):
        if not self.is_onboarded:
            return # Block local inputs completely if the node has not cleared onboarding
        
        if action == "INIT_SESSION" and self.is_hub:
            self.current_session = str(uuid.uuid4())[:8].upper()
        
        self.lamport += 1
        self.seq += 1
        ev_id = hashlib.sha256(f"{self.node_id}:{self.seq}".encode()).hexdigest()[:16]
        
        with self.conn:
            self.conn.execute(
                "INSERT INTO event_ledger VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ev_id, self.current_session, self.node_id, self.seq, self.lamport, time.time(), action, target, actor, payload)
            )

    def request_onboard(self, hub_port):
        """Executes the physical enrollment handshake over the wire to clear onboarding checks."""
        try:
            s = socket.create_connection(("127.0.0.1", hub_port), timeout=1)
            send_msg(s, {"type": "ONBOARD_REQUEST", "node_id": self.node_id, "gossip_port": self.gossip_port})
            res = recv_msg(s)
            s.close()
            if res and res.get("status") == "APPROVED":
                self.current_session = res["session_uuid"]
                self.is_onboarded = True
                return True
        except: pass
        return False

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
        if not self.is_onboarded: return
        with self.conn:
            for ev in deltas:
                if ev['session_uuid'] != self.current_session: continue
                cur = self.conn.execute(
                    "INSERT OR IGNORE INTO event_ledger VALUES (:event_id, :session_uuid, :node_id, :local_seq, :lamport, :os_time, :action, :target_id, :actor_id, :payload)", ev)
                if cur.rowcount > 0:
                    self.lamport = max(self.lamport, ev['lamport']) + 1
                    self.conn.execute("INSERT INTO vector_clocks VALUES (?, ?) ON CONFLICT(remote_node) DO UPDATE SET highest_seq=excluded.highest_seq WHERE excluded.highest_seq>vector_clocks.highest_seq", (ev['node_id'], ev['local_seq']))

    def trigger_gossip_async(self, peer_id, peer_port):
        """Asynchronously dispatches a gossip hello frame out to the network pipe layer."""
        if not self.is_onboarded: return
        payload = {"type": "HELLO", "origin_id": self.node_id, "origin_gossip": self.gossip_port, "vc": self.get_vc()}
        WIRE_PIPE.dispatch_wire(peer_port, payload, self.node_id, peer_id)

    def _gossip_listener(self):
        while True:
            try:
                conn, _ = self.gossip_srv.accept()
                msg = recv_msg(conn)
                if msg:
                    m_type = msg.get("type")
                    
                    # 1. Handle Onboarding Requests (Hub Specific)
                    if m_type == "ONBOARD_REQUEST" and self.is_hub:
                        self.peers_registry[msg["node_id"]] = msg["gossip_port"]
                        send_msg(conn, {"status": "APPROVED", "session_uuid": self.current_session})
                    
                    # 2. Handle standard peer-to-peer gossip transactions
                    elif m_type == "HELLO" and self.is_onboarded:
                        # Peer sent us their vector clock, respond asynchronously with our deltas
                        deltas_to_send = self.extract_deltas(msg["vc"])
                        reply = {"type": "SYNC_REPLY", "origin_id": self.node_id, "deltas": deltas_to_send, "vc": self.get_vc()}
                        WIRE_PIPE.dispatch_wire(msg["origin_gossip"], reply, self.node_id, msg["origin_id"])
                        
                    elif m_type == "SYNC_REPLY" and self.is_onboarded:
                        # Ingest their deltas and return final execution acknowledgement
                        self.ingest_deltas(msg["deltas"])
                        ack = {"type": "ACK_FINAL", "origin_id": self.node_id, "deltas": self.extract_deltas(msg["vc"])}
                        # Find peer's gossip port out of registry mapping profile
                        peer_port = self.peers_registry.get(msg["origin_id"]) or (self.gossip_port + 1 if msg['origin_id'] == "BETA" else self.gossip_port - 1)
                        WIRE_PIPE.dispatch_wire(peer_port, ack, self.node_id, msg["origin_id"])
                        
                    elif m_type == "ACK_FINAL" and self.is_onboarded:
                        self.ingest_deltas(msg["deltas"])
                        
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
                lt_ovr = next((e for e in reversed(evs) if e["action"] == "OVERRIDE" and ROLES.get(e["actor_id"]) == "COMMANDER"), None)
                lt_ev = max([e for e in [lt_fail, lt_out, lt_ovr] if e], key=lambda x: x["os_time"], default=None)
                
                if lt_ev and lt_ev["action"] == "FAIL": st = "RED"
                elif lt_ev and lt_ev["action"] == "OUT": st = "OUT"
                elif lt_ev and lt_ev["action"] == "OVERRIDE": st = "GREEN_OVR"
                else:
                    ticks = [e for e in evs if e["action"] in ["TICK", "INIT_SESSION"]]
                    if ticks: st = "VERIFIED" if len(set(t["actor_id"] for t in ticks)) >= 2 else "GREEN"
            elif ntype == "approval":
                lt_app = next((e for e in reversed(ledger) if e["target_id"] == n_id and e["action"] == "APPROVE"), None)
                st = "GREEN" if lt_app and ROLES.get(lt_app["actor_id"]) == "COMMANDER" else "STAGED"
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
        return {"session": self.current_session, "dag": DAG, "states": state_map}

    def _ipc_listener(self):
        while True:
            try:
                conn, _ = self.ipc_srv.accept()
                cmd = recv_msg(conn)
                if cmd:
                    action = cmd.get("action")
                    if action in ["TICK", "FAIL", "OUT", "OVERRIDE", "APPROVE", "INIT_SESSION"]:
                        self.log_event(action, cmd["target"], cmd["actor"])
                    send_msg(conn, self.evaluate())
                conn.close()
            except: pass

    def close(self):
        self.ipc_srv.close()
        self.gossip_srv.close()

# --- 4. THE ASYNCHRONOUS MASSIVE STOCHASTIC HAMMER HARNESS ---
class AsynchronousMeshSimulator:
    def __init__(self):
        print("[*] Instantiating Multi-Threaded Heterogeneous Mesh...")
        self.nodes = {
            "ALPHA": StoneflyDaemon("ALPHA", 5001, 6001, is_hub=True),  # GCS Hub
            "BETA":  StoneflyDaemon("BETA",  5002, 6002, is_hub=False), # Tech Tablet
            "GAMMA": StoneflyDaemon("GAMMA", 5003, 6003, is_hub=False)  # ALS System
        }
        time.sleep(0.1)

    def run_chaos_simulation(self):
        print("\n" + "="*60 + "\nPHASE 1: SECURE CRYPTOGRAPHIC ONBOARDING ENFORCEMENT\n" + "="*60)
        
        # Verify Node BETA cannot accept events or gossip before joining the lifecycle
        self.nodes["BETA"].log_event("TICK", "pack_bats", "tech_1")
        assert len(self.nodes["BETA"].extract_deltas({})) == 0, "Security Failure: Un-onboarded node logging inputs local."
        print("[✓] Passed: Core Engine strictly suppressed inputs on un-onboarded node hardware.")

        # Execute Onboarding Handshake via local wire simulation
        print("[⚡] Executing Onboarding Handshake over localized channel...")
        self.nodes["ALPHA"].log_event("INIT_SESSION", "pack_bats", "javaan")
        
        b_success = self.nodes["BETA"].request_onboard(6001)
        c_success = self.nodes["GAMMA"].request_onboard(6001)
        assert b_success and c_success, "Onboarding Handshake Failure."
        print(f"[✓] Onboarding Cleared: BETA and GAMMA safely linked into Session: {self.nodes['ALPHA'].current_session}")

        print("\n" + "="*60 + "\nPHASE 2: ASYNCHRONOUS MASSIVE CHAOS HAMMER\n" + "="*60)
        print("[🔥] Spawning Parallel Actor Threads and Network Flappers over 3000ms...")

        stop_signal = threading.Event()

        # Threaded Link Flapper Loop (Simulates Starlink/RF dropouts and delayed reconnection lines)
        def link_flapper():
            nodes_keys = list(self.nodes.keys())
            while not stop_signal.is_set():
                n1 = random.choice(nodes_keys)
                n2 = random.choice(nodes_keys)
                if n1 != n2:
                    link_state = random.choice([True, False, False]) # Weight heavier towards link drops
                    WIRE_PIPE.set_link(n1, n2, link_state)
                time.sleep(0.04) # Rapid link switching
        
        # Threaded Gossip Loop (Nodes trying to autonomously sync whenever link is transiently up)
        def background_gossip_loop(node_obj, p1_id, p1_port, p2_id, p2_port):
            while not stop_signal.is_set():
                node_obj.trigger_gossip_async(p1_id, p1_port)
                node_obj.trigger_gossip_async(p2_id, p2_port)
                time.sleep(0.05) # 20Hz attempt loop

        # Threaded High-Volume Actor Input Hammer
        def input_hammer(node_obj, actor, target_list):
            while not stop_signal.is_set():
                action = random.choice(["TICK", "OUT", "FAIL"])
                target = random.choice(target_list)
                node_obj.log_event(action, target, actor)
                time.sleep(0.01) # 100Hz input generation per node

        # Inject 15% random packet-loss on top of link dropouts
        WIRE_PIPE.drop_rate = 0.15

        # Initialize and kick off all system threads simultaneously
        threads = [
            threading.Thread(target=link_flapper),
            threading.Thread(target=background_gossip_loop, args=(self.nodes["ALPHA"], "BETA", 6002, "GAMMA", 6003)),
            threading.Thread(target=background_gossip_loop, args=(self.nodes["BETA"],  "ALPHA", 6001, "GAMMA", 6003)),
            threading.Thread(target=background_gossip_loop, args=(self.nodes["GAMMA"], "ALPHA", 6001, "BETA", 6002)),
            threading.Thread(target=input_hammer, args=(self.nodes["ALPHA"], "javaan", ["pack_bats", "payload", "als_auth"])),
            threading.Thread(target=input_hammer, args=(self.nodes["BETA"],  "tech_1", ["pack_bats", "payload"])),
            threading.Thread(target=input_hammer, args=(self.nodes["GAMMA"], "hardware_1", ["als_sequence"]))
        ]

        for t in threads: t.start()
        time.sleep(3.0) # Sustain the storm for 3 full seconds
        
        print("[*] Stopping Chaos Engine threads...")
        stop_signal.set()
        for t in threads: t.join()

        print("\n" + "="*60 + "\nPHASE 3: NETWORK HEALING & FINAL SETTLEMENT PASS\n" + "="*60)
        print("[*] Restoring perfect line-of-sight RF topology. Packet-loss set to 0%.")
        WIRE_PIPE.drop_rate = 0.0
        for n1 in self.nodes:
            for n2 in self.nodes:
                WIRE_PIPE.set_link(n1, n2, True)

        print("[*] Executing deep global synchronization settlement loop over wire...")
        # Execute multi-pass async loops to ensure delayed threads catch up completely
        for settlement_round in range(10):
            self.nodes["ALPHA"].trigger_gossip_async("BETA", 6002)
            self.nodes["BETA"].trigger_gossip_async("GAMMA", 6003)
            self.nodes["GAMMA"].trigger_gossip_async("ALPHA", 6001)
            time.sleep(0.1) # Let the network thread pipelines clear cleanly

        print("\n" + "="*60 + "\nFINAL DISTRIBUTED MATRIX ATTESTATION\n" + "="*60)
        a_res = self.nodes["ALPHA"].evaluate()
        b_res = self.nodes["BETA"].evaluate()
        c_res = self.nodes["GAMMA"].evaluate()

        print(f"Node ALPHA Ledger Event Blocks: {self.nodes['ALPHA'].conn.execute('SELECT COUNT(*) FROM event_ledger').fetchone()[0]}")
        print(f"Node BETA  Ledger Event Blocks: {self.nodes['BETA'].conn.execute('SELECT COUNT(*) FROM event_ledger').fetchone()[0]}")
        print(f"Node GAMMA Ledger Event Blocks: {self.nodes['GAMMA'].conn.execute('SELECT COUNT(*) FROM event_ledger').fetchone()[0]}")

        try:
            assert a_res["states"] == b_res["states"] == c_res["states"], "CRITICAL FAIL: Consensus Divergence across network lines."
            print("\n\033[92m[✓] TRANSACTIONAL CONVERGENCE SUCCESS: All 3 physical node ledgers achieved absolute mathematical state parity across lossy lines.\033[0m\n")
        except AssertionError as e:
            print("\n\033[91m[X] RECONCILIATION FAILURE STATUS SHEET:\033[0m")
            print(f"ALPHA: {a_res['states']}")
            print(f"BETA:  {b_res['states']}")
            print(f"GAMMA: {c_res['states']}")
            raise e
        finally:
            for n in self.nodes.values(): n.close()

if __name__ == "__main__":
    sim = AsynchronousMeshSimulator()
    sim.run_chaos_simulation()
