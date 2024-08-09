import heapq


class Env:
    def __init__(self):
        # Initialize rooms and assets
        self.rooms = ["Kitchen", "Living Room", "Restroom", "Bedroom"]
        self.assets = {
            "Kitchen": ["Table", "Toaster", "Sink", "Refrigerator", "Stove", "Pan"],
            "Living Room": ["Table", "Sofa", "Television", "Laundry Basket"],
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
                # Add default cost for moving from room to asset
                self.add_transition(room, asset_node, 0.25)

    def __repr__(self):
        return str(self.graph)

    def add_transition(self, node1, node2, cost):
        if node1 in self.graph and node2 in self.graph:
            self.graph[node1][node2] = cost
            self.graph[node2][node1] = cost
        else:
            raise ValueError("Both nodes must be in the graph.")

    def gen_dummy(self):
        # Add room to room transitions
        self.add_transition("Kitchen", "Living Room", 0.5)
        self.add_transition("Living Room", "Restroom", 0.5)
        self.add_transition("Living Room", "Bedroom", 0.5)

        # Add asset to asset transitions within rooms
        self.add_transition("Kitchen:Table", "Kitchen:Toaster", 0.25)
        self.add_transition("Kitchen:Toaster", "Kitchen:Sink", 0.25)
        self.add_transition("Kitchen:Sink", "Kitchen:Refrigerator", 0.25)
        self.add_transition("Kitchen:Stove", "Kitchen:Pan", 0.25)
        self.add_transition("Kitchen:Sink", "Kitchen:Stove", 0.25)

        self.add_transition("Living Room:Table", "Living Room:Sofa", 0.25)
        self.add_transition("Living Room:Sofa", "Living Room:Television", 0.25)

        self.add_transition("Restroom:Laundry Basket", "Restroom:Washing Machine", 0.25)
        self.add_transition("Restroom:Washing Machine", "Restroom:Dryer", 0.25)
        self.add_transition("Restroom:Sink", "Restroom:Toilet", 0.25)

        self.add_transition("Bedroom:Bed", "Bedroom:Wardrobe", 0.25)
        self.add_transition("Bedroom:Wardrobe", "Bedroom:Desk", 0.25)

    def get_cost(self, departure: str, destination: str) -> int:

        def dijkstra(start, goal):
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

        # Normalize input for asset queries
        if ":" not in departure:
            departure = self.normalize_room_or_asset(departure)
        if ":" not in destination:
            destination = self.normalize_room_or_asset(destination)

        return dijkstra(departure, destination)

    def normalize_room_or_asset(self, name: str) -> str:
        # Normalize names to include room:asset notation if needed
        for room, assets in self.assets.items():
            if name == room:
                return room
            if name in assets:
                return f"{room}:{name}"
        raise ValueError(f"Name {name} not found in rooms or assets.")
