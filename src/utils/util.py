import os
import signal


# with timeout(seconds=timeout_seconds):
class timeout:
    def __init__(self, seconds=1, error_message="Timeout"):
        self.seconds = seconds
        self.error_message = error_message

    def handle_timeout(self, signum, frame):
        raise TimeoutError(self.error_message)

    def __enter__(self):
        signal.signal(signal.SIGALRM, self.handle_timeout)
        signal.alarm(self.seconds)

    def __exit__(self, type, value, traceback):
        signal.alarm(0)


def get_paths_to_leaves(root):
    paths = []

    # Traverse the tree to gather task paths
    def traverse_tree(node, current_path):
        if not node.children:  # If it's a leaf node, store the path
            paths.append(current_path + [node])
        for child in node.children:
            traverse_tree(child, current_path + [node])

    traverse_tree(root, [])
    return paths
