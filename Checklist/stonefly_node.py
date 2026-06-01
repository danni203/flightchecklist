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
ROLES = {"tech_1": "OPERATOR", "tech_2": "OPERATOR", "hardware_1": "SYSTEM", "javaan": "COMMANDER"}
MANIFEST = {
    "org": "STONEFLY \U0001F870", "platform": "Project Icarus \u2708\uFE0F",
    "themes": {"night": {"bg": "\033[40m", "fg": "\033[37m", "GREEN": "\033[92m", "VERIFIED": "\033[96m", "AMBER": "\033[93m", "RED": "\033[91m", "OUT": "\033[90m", "STAGED": "\033[95m", "BLOCKED": "\033[31m"}}
}
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
        
        self.lamport += 1
        self.seq += 1
        ev_id = hashlib.sha256(f"{self.node_id}:{self.seq}".encode()).hexdigest()[:16]
        
        with self.conn:
            self.conn.execute(
                "INSERT INTO event_ledger VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ev_id, self.current_session, self.node_id, self.seq, self.lamport, time.time(), action, target, actor, payload)
            )

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
                lt_ovr = next((e for e in reversed(evs) if e["action"] == "OVERRIDE" and ROLES.get(e["actor_id"]) == "COMMANDER"), None)
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
        return {"session": self.current_session, "dag": DAG}

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
