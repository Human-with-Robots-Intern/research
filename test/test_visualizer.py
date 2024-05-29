import unittest

from visualization import ScheduleVisualizer


class TestScheduleVisualizer(unittest.TestCase):
    def test_visualize(self):
        # Sample schedule
        schedule = [
            ("Test_Task_Start", 0, 5),
            ("Test_Task_Continue", 5, 15),
            ("Test_Task_End", 15, 20),
        ]

        # Ensure the visualize method runs without errors
        try:
            ScheduleVisualizer.visualize(schedule)
        except Exception as e:
            self.fail(f"ScheduleVisualizer.visualize() raised an exception: {e}")


if __name__ == "__main__":
    unittest.main()
