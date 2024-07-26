import unittest

from concept.env import Env


class TestEnv(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.env.gen_dummpy()

    def test_initialization(self):
        expected_rooms = ["Kitchen", "Living Room", "Restroom", "Bedroom"]
        self.assertEqual(set(self.env.rooms), set(expected_rooms))
        for room in expected_rooms:
            self.assertIn(room, self.env.graph)
            self.assertIsInstance(self.env.graph[room], dict)

    def test_add_transition(self):
        self.env.add_transition("Kitchen", "Bedroom", 2)
        self.assertIn("Bedroom", self.env.graph["Kitchen"])
        self.assertIn("Kitchen", self.env.graph["Bedroom"])
        self.assertEqual(self.env.graph["Kitchen"]["Bedroom"], 2)
        self.assertEqual(self.env.graph["Bedroom"]["Kitchen"], 2)

    def test_gen_dummpy(self):
        self.env.gen_dummpy()
        self.assertIn("Living Room", self.env.graph["Kitchen"])
        self.assertIn("Restroom", self.env.graph["Living Room"])
        self.assertIn("Bedroom", self.env.graph["Living Room"])
        self.assertEqual(self.env.graph["Kitchen"]["Living Room"], 1)
        self.assertEqual(self.env.graph["Living Room"]["Restroom"], 1)
        self.assertEqual(self.env.graph["Living Room"]["Bedroom"], 1)

    def test_get_cost(self):
        cost = self.env.get_cost("Kitchen", "Restroom")
        self.assertEqual(cost, 2)
        cost = self.env.get_cost("Kitchen", "Bedroom")
        self.assertEqual(cost, 2)
        cost = self.env.get_cost("Restroom", "Bedroom")
        self.assertEqual(cost, 2)
        with self.assertRaises(ValueError):
            self.env.get_cost("Kitchen", "NonExistentRoom")


if __name__ == "__main__":
    unittest.main()
