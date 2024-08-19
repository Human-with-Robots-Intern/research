import heapq


class Env:
    def __init__(self):
        # Initialize rooms and assets
        self.rooms = ["Kitchen", "Living Room", "Restroom", "Bedroom"]
        self.assets = {
            "Kitchen": [
                "Table",
                "Toaster",
                "Sink",
                "Refrigerator",
                "Stove",
                "Pan",
                "Pot",
                "Counter",
            ],
            "Living Room": ["Table", "Sofa", "Television", "Laundry Basket", "Floor"],
            "Restroom": [
                "Laundry Basket",
                "Washing Machine",
                "Dryer",
                "Sink",
                "Toilet",
            ],
            "Bedroom": ["Bed", "Wardrobe", "Desk"],
        }
        # Graph includes both rooms and assets
        self.graph = {room: {} for room in self.rooms}
        for room in self.assets:
            for asset in self.assets[room]:
                asset_node = f"{room}:{asset}"
                self.graph[asset_node] = {}
                self.graph[asset_node][asset_node] = 0
                # Add default cost for moving from room to asset
                self._add_transition(room, asset_node, 0.25)

    def __repr__(self):
        return str(self.graph)

    def _add_transition(self, node1, node2, cost):
        if node1 in self.graph and node2 in self.graph:
            self.graph[node1][node2] = cost
            self.graph[node2][node1] = cost
        else:
            raise ValueError("Both nodes must be in the graph.")

    def gen_dummy(self):

        room_transitions = [
            ("Kitchen", "Living Room", 0.5),
            ("Living Room", "Restroom", 0.5),
            ("Living Room", "Bedroom", 0.5),
        ]
        for node1, node2, cost in room_transitions:
            self._add_transition(node1, node2, cost)

        asset_transitions = {
            "Kitchen": [
                ("Table", "Toaster"),
                ("Toaster", "Sink"),
                ("Sink", "Refrigerator"),
                ("Stove", "Pan"),
                ("Sink", "Stove"),
            ],
            "Living Room": [
                ("Sofa", "Television"),
            ],
            "Restroom": [
                ("Laundry Basket", "Washing Machine"),
                ("Washing Machine", "Dryer"),
                ("Sink", "Toilet"),
            ],
            "Bedroom": [
                ("Bed", "Wardrobe"),
                ("Wardrobe", "Desk"),
            ],
        }

        for room, transitions in asset_transitions.items():
            for asset1, asset2 in transitions:
                asset1_node = f"{room}:{asset1}"
                asset2_node = f"{room}:{asset2}"
                self._add_transition(asset1_node, asset2_node, 0.25)

    def get_cost(self, departure: str, destination: str) -> int:
        departure = self._normalize_name(departure)
        destination = self._normalize_name(destination)

        return self._dijkstra(departure, destination)

    def _normalize_name(self, name: str) -> str:
        # Normalize names to include room:asset notation if needed
        name = name.split(":")[1] if ":" in name else name

        for room, assets in self.assets.items():
            if name == room:
                return room
            if name in assets:
                return f"{room}:{name}"
        raise ValueError(f"Name {name} not found in rooms or assets.")

    def _dijkstra(self, start, goal):
        # Priority queue: (cost, node)
        queue = [(0, start)]
        visited = {}
        while queue:
            current_cost, current_node = heapq.heappop(queue)
            if current_node in visited:
                continue
            visited[current_node] = current_cost
            if current_node == goal:
                return current_cost

            for neighbor, cost in self.graph[current_node].items():
                if neighbor not in visited:
                    heapq.heappush(queue, (current_cost + cost, neighbor))

        raise ValueError("No path found between the given nodes.")
