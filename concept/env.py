import heapq


class Env:
    def __init__(self):
        self.rooms = ["Kitchen", "Living Room", "Restroom", "Bedroom"]
        self.graph = {room: {} for room in self.rooms}

    def __repr__(self):
        return str(self.graph)

    def add_transition(self, room1, room2, cost):
        if room1 in self.graph and room2 in self.graph:
            self.graph[room1][room2] = cost
            self.graph[room2][room1] = cost
        else:
            raise ValueError("Both rooms must be in the graph.")

    def gen_dummpy(self):
        self.add_transition("Kitchen", "Living Room", 1)
        self.add_transition("Living Room", "Restroom", 1)
        self.add_transition("Living Room", "Bedroom", 1)

    def get_cost(self, departure, destination):

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

        return dijkstra(departure, destination)
