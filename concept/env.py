import heapq
from collections import namedtuple


class Env:
    def __init__(self, current_location="Kitchen"):
        self.rooms = ["Kitchen", "Living Room", "Restroom", "Bedroom"]
        self.graph = {room: {} for room in self.rooms}
        self.current_location = current_location

    def add_transition(self, room1, room2, cost):
        if room1 in self.graph and room2 in self.graph:
            self.graph[room1][room2] = cost
            self.graph[room2][room1] = cost
        else:
            raise ValueError("Both rooms must be in the graph.")

    def get_cost(self, goal):
        if (
            self.current_location in self.graph
            and goal in self.graph[self.current_location]
        ):
            return self.graph[self.current_location][goal]
        elif self.current_location == goal:
            return 0
        else:
            return self.dijkstra(self.current_location, goal)

    def __repr__(self):
        return str(self.graph)

    def dijkstra(self, start, goal):
        # Priority queue: (cost, node)
        queue = [(0, start)]
        visited = {}
        while queue:
            current_cost, current_room = heapq.heappop(queue)
            if current_room in visited:
                continue
            visited[current_room] = current_cost
            if current_room == goal:
                return current_cost

            for neighbor, cost in self.graph[current_room].items():
                if neighbor not in visited:
                    heapq.heappush(queue, (current_cost + cost, neighbor))

        raise ValueError("No path found between the given rooms.")

    def gen_dummpy(self, current_location):
        self.current_location = current_location
        self.add_transition("Kitchen", "Living Room", 5)
        self.add_transition("Living Room", "Restroom", 2)
        self.add_transition("Restroom", "Bedroom", 3)
        self.add_transition("Bedroom", "Kitchen", 4)

    def move(self, goal):
        name = f"Move from {self.current_location} to {goal}"
        duration = self.get_cost(goal)
        self.current_location = goal
        Move = namedtuple("Move", ["name", "duration"])

        return Move(name, duration)
