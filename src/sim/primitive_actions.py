import time

from omnigibson.action_primitives.starter_semantic_action_primitives import (
    StarterSemanticActionPrimitives,
)
from utils.util import timeit


class CustomActionPrimitives(StarterSemanticActionPrimitives):
    def __init__(self, env, bayesian_agent: "BayesianAgent"):
        self.bayesian_agent = bayesian_agent
        self.env = env
        super().__init__(env, enable_head_tracking=False)

    @property
    def robot(self):
        return self.bayesian_agent.robot_attribute

    def apply_primitive_action(self, prim, *args, attempts=4):
        @timeit
        def _execute_controller(ctrl_gen, env):
            for action in ctrl_gen:
                env.step(action)

        elapsed_time = _execute_controller(
            super().apply_ref(prim, *args, attempts=attempts), self.env
        )
        print(f"Primitive action {prim.name} took {elapsed_time:.2f} seconds")
        self.bayesian_agent.update_primitive_action_knowledge(prim.name, elapsed_time)
        return
