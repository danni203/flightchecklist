import sqlite3
import time
import hashlib
import json
from typing import List, Dict

class DistributedLedger:
    def __init__(self, db_path: str, node_id: str):
        self.node_id = node_id
        # Using check_same_thread=False allows background sync daemons to share the connection
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lamport_clock = 0
        self.local_seq = 0
        
        self._init_schema()
        self._load_local_state()

    def _init_schema(self):
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
                    remote_node_id TEXT PRIMARY KEY,
                    highest_seq INTEGER NOT NULL
                );
            ''')

    def _load_local_state(self):
        """Restores clock vectors from persistent storage on boot."""
        cur = self.conn.cursor()
        cur.execute("SELECT MAX(lamport_clock) FROM event_ledger")
        res = cur.fetchone()[0]
        self.lamport_clock = res if res is not None else 0

        cur.execute("SELECT MAX(local_seq) FROM event_ledger WHERE node_id = ?", (self.node_id,))
        res = cur.fetchone()[0]
        self.local_seq = res if res is not None else 0

    def log_local_event(self, action: str, target_id: str, actor_id: str, payload: str = "") -> dict:
        """Appends a new local reality to the ledger and increments clocks."""
        self.lamport_clock += 1
        self.local_seq += 1
        os_time = time.time()
        
        # Deterministic primary key
        event_id = hashlib.sha256(f"{self.node_id}:{self.local_seq}".encode()).hexdigest()[:16]

        event = {
            "event_id": event_id, "node_id": self.node_id, "local_seq": self.local_seq,
            "lamport_clock": self.lamport_clock, "os_time": os_time,
            "action": action, "target_id": target_id, "actor_id": actor_id, "payload": payload
        }

        with self.conn:
            self.conn.execute('''
                INSERT INTO event_ledger 
                (event_id, node_id, local_seq, lamport_clock, os_time, action, target_id, actor_id, payload)
                VALUES (:event_id, :node_id, :local_seq, :lamport_clock, :os_time, :action, :target_id, :actor_id, :payload)
            ''', event)
        return event

    # --- SYNCHRONIZATION HANDSHAKE LOGIC ---

    def get_vector_clock(self) -> Dict[str, int]:
        """Returns the high-water marks of what this node has already seen."""
        cur = self.conn.cursor()
        cur.execute("SELECT remote_node_id, highest_seq FROM vector_clocks")
        vc = {row['remote_node_id']: row['highest_seq'] for row in cur.fetchall()}
        vc[self.node_id] = self.local_seq  # Inject local high-water mark
        return vc

    def extract_deltas(self, remote_vc: Dict[str, int]) -> List[dict]:
        """Returns events the remote node is missing based on its vector clock."""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM event_ledger ORDER BY lamport_clock ASC")
        all_events = [dict(row) for row in cur.fetchall()]
        
        delta = []
        for ev in all_events:
            n_id = ev['node_id']
            # If we don't know the node, or the event seq is higher than what they've seen
            if n_id not in remote_vc or ev['local_seq'] > remote_vc[n_id]:
                delta.append(ev)
        return delta

    def ingest_deltas(self, incoming_events: List[dict]):
        """Absorbs remote events, updates logical clocks, and recalculates high-water marks."""
        if not incoming_events: 
            return
            
        with self.conn:
            for ev in incoming_events:
                # INSERT OR IGNORE provides native idempotency. If network packet duplicates, SQLite drops it safely.
                cur = self.conn.execute('''
                    INSERT OR IGNORE INTO event_ledger 
                    (event_id, node_id, local_seq, lamport_clock, os_time, action, target_id, actor_id, payload)
                    VALUES (:event_id, :node_id, :local_seq, :lamport_clock, :os_time, :action, :target_id, :actor_id, :payload)
                ''', ev)
                
                if cur.rowcount > 0:  # New event was successfully ingested
                    self.lamport_clock = max(self.lamport_clock, ev['lamport_clock']) + 1
                    
                    self.conn.execute('''
                        INSERT INTO vector_clocks (remote_node_id, highest_seq) 
                        VALUES (?, ?)
                        ON CONFLICT(remote_node_id) DO UPDATE SET 
                        highest_seq = excluded.highest_seq 
                        WHERE excluded.highest_seq > vector_clocks.highest_seq
                    ''', (ev['node_id'], ev['local_seq']))

    def get_ordered_ledger(self) -> List[dict]:
        """Returns the cryptographically sorted reality for the DAG Evaluator."""
        cur = self.conn.cursor()
        # The primary sort is logical time. Node_ID prevents race conditions. Sequence is the final tie-breaker.
        cur.execute("SELECT * FROM event_ledger ORDER BY lamport_clock ASC, node_id ASC, local_seq ASC")
        return [dict(row) for row in cur.fetchall()]


if __name__ == "__main__":
    # --- TEST HARNESS: OFFLINE OPERATIONS & RESYNC ---
    
    print("\033[1m--- INITIALIZING DISTRIBUTED NODES ---\033[0m")
    # Using :memory: for the test, but maps exactly to file paths on hardware
    hub = DistributedLedger(":memory:", "GCS_Hub")
    tablet = DistributedLedger(":memory:", "Android_Tablet_Alpha")

    # 1. Concurrent Offline Operations
    print("Hub logs Engine Prep (Offline)")
    hub.log_local_event("TICK", "fuel_prime", "tech_1")
    
    print("Tablet logs Depot Prep (Offline)")
    tablet.log_local_event("TICK", "pack_bats", "tech_2")
    tablet.log_local_event("TICK", "inspect_frame", "tech_2")

    # 2. The Vector Clock Handshake (Simulating Starlink connection restoration)
    print("\n\033[1m--- EXECUTING VECTOR CLOCK HANDSHAKE ---\033[0m")
    hub_vc = hub.get_vector_clock()
    tablet_vc = tablet.get_vector_clock()

    print(f"Hub's Knowledge Matrix: {hub_vc}")
    print(f"Tablet's Knowledge Matrix: {tablet_vc}")

    # Exchange Deltas
    payload_to_hub = tablet.extract_deltas(hub_vc)
    payload_to_tablet = hub.extract_deltas(tablet_vc)

    # Ingest Deltas
    hub.ingest_deltas(payload_to_hub)
    tablet.ingest_deltas(payload_to_tablet)

    # 3. Verify Deterministic Convergence
    print("\n\033[1m--- VERIFYING CAUSAL SORTING ---\033[0m")
    hub_reality = [(e['lamport_clock'], e['node_id'], e['action'], e['target_id']) for e in hub.get_ordered_ledger()]
    tablet_reality = [(e['lamport_clock'], e['node_id'], e['action'], e['target_id']) for e in tablet.get_ordered_ledger()]

    assert hub_reality == tablet_reality, "CRITICAL FAULT: Ledger divergence."

    print("Convergence confirmed. Both nodes materialized identical ordered histories:")
    for event in hub_reality:
        print(f"  [L-Clock: {event[0]}] {event[1].ljust(22)} | {event[2]} -> {event[3]}")
    print("\n")
