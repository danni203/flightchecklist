# cycle_h_interfaces.py (Part 1: LLM API)
import json

class LLM_Interface:
    def __init__(self, ledger, evaluator):
        self.ledger = ledger
        self.evaluator = evaluator
        self.llm_actor_id = "agent_omega" # The LLM's assigned RBAC identity

    def refresh_state(self, current_time: float):
        """Materializes the latest state from the ledger."""
        ordered_history = self.ledger.get_ordered_ledger()
        self.evaluator.evaluate_graph(ordered_history, current_time)

    def get_node_state(self, node_id: str) -> str:
        """Endpoint for the LLM to query a specific checklist item."""
        node = self.evaluator.node_index.get(node_id)
        if not node:
            return json.dumps({"error": f"Node {node_id} not found."})
        
        response = {
            "node_id": node["node_id"],
            "name": node["name"],
            "status": node["status"]
        }
        if "ttl_minutes" in node:
            response["ttl_minutes"] = node["ttl_minutes"]
        return json.dumps(response)

    def get_critical_path(self) -> str:
        """Calculates exactly what is preventing the next Barrier from clearing."""
        # Find all nodes causing a block (i.e., prerequisites not met)
        blockers = []
        for node_id, status in self.evaluator.state_map.items():
            if status in ["UNINITIALIZED", "AMBER", "RED"]:
                # Only surface leaf nodes to the LLM to give actionable intelligence
                node = self.evaluator.node_index[node_id]
                if node.get("node_type") == "leaf":
                    blockers.append({"node_id": node_id, "name": node["name"], "status": status})
        
        return json.dumps({"active_blockers": blockers})

    def append_action(self, node_id: str, action: str, payload: str = "", current_time: float = 0.0) -> str:
        """Endpoint for the LLM to tick a checklist item or flag an anomaly."""
        valid_actions = ["TICK", "FLAG_ANOMALY"]
        if action not in valid_actions:
            return json.dumps({"error": f"Action must be one of {valid_actions}"})
        
        event = self.ledger.log_local_event(action, node_id, self.llm_actor_id, payload, current_time)
        return json.dumps({"status": "Success", "event_id": event["event_id"]})
