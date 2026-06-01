# cycle_h_interfaces.py (Part 2: UDP Emitter)
import socket
import time
import threading

class JINST_Telemetry_Emitter:
    def __init__(self, evaluator, host="255.255.255.255", port=49152):
        self.evaluator = evaluator
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._running = False

    def _serialize_payload(self) -> bytes:
        """Packages the root graph state and alarms into a compact JINST telemetry frame."""
        root_node = self.evaluator.root_dag
        
        # Extract highest severity status for the system overhead
        sys_status = root_node.get("status", "UNKNOWN")
        
        payload = {
            "sys_id": "STONEFLY_ICARUS",
            "timestamp": time.time(),
            "root_status": sys_status,
            # For minimal bandwidth, only transmit degraded node IDs
            "degraded_nodes": [
                n_id for n_id, status in self.evaluator.state_map.items() 
                if status in ["AMBER", "RED", "BLOCKED"]
            ]
        }
        return json.dumps(payload).encode('utf-8')

    def start_emission(self, hz: float = 1.0):
        """Runs the UDP broadcaster in a background thread."""
        self._running = True
        def loop():
            while self._running:
                try:
                    data = self._serialize_payload()
                    self.sock.sendto(data, (self.host, self.port))
                except Exception as e:
                    pass # Fail silently in telemetry loops to prevent thread crashes
                time.sleep(1.0 / hz)
                
        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()

    def stop(self):
        self._running = False
        if hasattr(self, 'thread'):
            self.thread.join()
