from concept.env import Env


class Agent:
    def __init__(self, status: str, location: str, env: Env):
        """Agent status management
        Args:
            status (str): Waiting / Running / Monitoring(?)
            location (str): current_location
        """
        self.status = status
        self.location = location
        self.env = env
        self.trajectory = []

    def move(self, goal):
        move_cost = self.env.get_cost(self.location, goal)
        self.location = goal
        return move_cost
