import unittest

from concept import Env


class TestEnv(unittest.TestCase):

    def setUp(self):
        self.env = Env()

    def test_initial_location(self):
        self.assertEqual(self.env.current_location, "Kitchen")

    def test_add_transition(self):
        self.env.add_transition("Kitchen", "Living Room", 1)
        self.assertEqual(self.env.graph["Kitchen"]["Living Room"], 1)
        self.assertEqual(self.env.graph["Living Room"]["Kitchen"], 1)

    def test_get_cost_direct_path(self):
        self.env.add_transition("Kitchen", "Living Room", 1)
        self.assertEqual(self.env.get_cost("Living Room"), 1)
        self.assertEqual(self.env.get_cost("Kitchen"), 0)

    def test_get_cost_via_dijkstra(self):
        self.env.add_transition("Kitchen", "Living Room", 1)
        self.env.add_transition("Living Room", "Restroom", 2)
        self.assertEqual(self.env.get_cost("Restroom"), 3)

    def test_no_path(self):
        self.env.add_transition("Kitchen", "Living Room", 1)
        with self.assertRaises(ValueError):
            self.env.get_cost("Bedroom")

    def test_move(self):
        self.env.add_transition("Kitchen", "Living Room", 1)
        move = self.env.move("Living Room")
        self.assertEqual(move.name, "Move from Kitchen to Living Room")
        self.assertEqual(move.duration, 1)
        self.assertEqual(self.env.current_location, "Living Room")

    def test_repr(self):
        self.env.add_transition("Kitchen", "Living Room", 1)
        self.env.add_transition("Living Room", "Restroom", 2)
        expected_repr = "{'Kitchen': {'Living Room': 1}, 'Living Room': {'Kitchen': 1, 'Restroom': 2}, 'Restroom': {'Living Room': 2}, 'Bedroom': {}}"
        self.assertEqual(repr(self.env), expected_repr)

    def test_gen_dummpy(self):
        self.env.gen_dummpy("Living Room")
        expected_graph = {
            "Kitchen": {"Living Room": 1},
            "Living Room": {"Kitchen": 1, "Restroom": 2},
            "Restroom": {"Living Room": 2},
            "Bedroom": {},
        }
        self.assertEqual(self.env.graph, expected_graph)
        self.assertEqual(self.env.current_location, "Living Room")


if __name__ == "__main__":
    unittest.main()
