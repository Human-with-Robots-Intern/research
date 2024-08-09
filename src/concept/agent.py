from concept.env import Env


class Agent:
    def __init__(self, status: str, location: str, env: Env):
        """Agent status management

        Args:
            status (str): Waiting / Running / Monitoring(?)
            location (str): current_location (Room or Asset)
        """
        self.status = status
        self.env = env
        self.location = self.normalize_location(location)

    def normalize_location(self, location: str) -> str:
        """
        Normalize the location to ensure it is in the correct format for rooms or assets.

        Args:
            location (str): The location name (room or asset).

        Returns:
            str: Normalized location name in the format 'Room' or 'Room:Asset'.
        """
        try:
            return self.env.normalize_room_or_asset(location)
        except ValueError as e:
            print(f"Error: {e}")
            return location

    def move(self, goal: str) -> int:
        """
        Move the agent to a new location and update its trajectory.

        Args:
            goal (str): The destination location.

        Returns:
            int: The cost of moving to the goal location.
        """
        goal = self.normalize_location(goal)
        move_cost = self.env.get_cost(self.location, goal)
        self.location = goal

        return move_cost

    def get_move_cost(self, goal: str) -> int:
        goal = self.normalize_location(goal)
        move_cost = self.env.get_cost(self.location, goal)
        return move_cost

    def __repr__(self):
        return f"Agent(status={self.status}, location={self.location}"
