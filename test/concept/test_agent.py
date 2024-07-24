import unittest

from concept.agent import Agent
from concept.env import Env


class TestAgent(unittest.TestCase):
    def setUp(self):
        # Set up environment and generate dummy data
        self.env = Env()
        self.env.gen_dummpy()

        # Create an agent with initial status and location
        self.agent = Agent(status="Waiting", location="Kitchen", env=self.env)

    def test_agent_initialization(self):
        self.assertEqual(self.agent.status, "Waiting")
        self.assertEqual(self.agent.location, "Kitchen")
        self.assertIs(self.agent.env, self.env)

    def test_agent_move(self):
        # Test moving from Kitchen to Living Room
        move_cost = self.agent.move("Living Room")
        self.assertEqual(move_cost, 1)
        self.assertEqual(self.agent.location, "Living Room")

        # Test moving from Living Room to Restroom
        move_cost = self.agent.move("Restroom")
        self.assertEqual(move_cost, 1)
        self.assertEqual(self.agent.location, "Restroom")

        # Test moving from Restroom to Bedroom through Living Room
        move_cost = self.agent.move("Bedroom")
        self.assertEqual(move_cost, 2)
        self.assertEqual(self.agent.location, "Bedroom")

        # Test moving to a non-existent room
        with self.assertRaises(ValueError):
            self.agent.move("NonExistentRoom")


if __name__ == "__main__":
    unittest.main()
