import json
import os

from concept.env import Env
from utils.constants import ROOT_PATH


class Agent:
    def __init__(self, status: str, location: str, env: Env):
        """Agent status management

        Args:
            status (str): Waiting / Running / Monitoring(?)
            location (str): current_location (Room or Assets)
        """
        self.status = status
        self.env = env
        self.location = location

    def move(self, goal: str) -> int:
        move_cost = self.env.get_cost(self.location, goal)

        self.location = self.env._normalize_name(goal)

        return move_cost

    def __repr__(self):
        return f"Agent(status={self.status}, location={self.location}"
