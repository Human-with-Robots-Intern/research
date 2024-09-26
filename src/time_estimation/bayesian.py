import numpy as np
from scipy.stats import norm


class Config:
    def __init__(self, criteria=0.7, interval=0.1, obs_dur=0.01):
        self.criteria = criteria
        self.interval = interval
        self.obs_dur = obs_dur


class TaskInfo:
    def __init__(self, idx, plan_task, sim_task, start_time):
        self.idx = idx
        self.plan_task = plan_task
        self.sim_task = sim_task
        self.start_time = start_time


class TaskEstimator:
    def __init__(self, config=None):
        if config is None:
            config = Config()
        self.config = config

    def bayesian_estimation(self, dist, elapsed_time, obs_var=0.001):
        prior_mean, prior_variance = dist.mean(), dist.var()
        if prior_variance < 1e-6:
            prior_variance = 1e-6

        try:
            updated_mean = (prior_mean / prior_variance + elapsed_time / obs_var) / (
                1 / prior_variance + 1 / obs_var
            )
            updated_variance = 1 / (1 / prior_variance + 1 / obs_var)
            if not (np.isfinite(updated_mean) and np.isfinite(updated_variance)):
                updated_mean, updated_variance = prior_mean, prior_variance
                print("Warning: NaN encountered, using prior values.")
            dist = norm(loc=updated_mean, scale=max(updated_variance**0.5, 1e-3))
        except Exception as e:
            print(f"Exception during estimation: {e}, using prior values.")
            dist = norm(loc=prior_mean, scale=max(prior_variance**0.5, 1e-3))

        print(f"   [Estimation] Mean updated: {prior_mean:.2f} -> {updated_mean:.2f}")
        return dist

    def run_task(self, task_info):
        print("\n===================================")
        print(f"Task {task_info.idx + 1}: {task_info.plan_task.name}")
        print("-----------------------------------")
        print(
            f"  - Planned Task Schedule Info: {task_info.plan_task.start:.2f} ~ {task_info.plan_task.end:.2f} ({task_info.plan_task.duration:.2f})"
        )
        print(
            f"  - Noise Task Schedule Info: {task_info.sim_task.start:.2f} ~ {task_info.sim_task.end:.2f} ({task_info.sim_task.duration:.2f})"
        )
        print("-----------------------------------")

        task_duration_dist = norm(
            loc=task_info.plan_task.duration, scale=(task_info.plan_task.duration / 2)
        )
        t_c = task_info.start_time

        while True:
            t_c += self.config.interval
            elapsed_time = t_c - task_info.start_time

            if task_duration_dist.cdf(elapsed_time) >= self.config.criteria:
                print(f"   [Time: {t_c:.2f}] Elapsed: {elapsed_time:.2f}", end="")
                task_duration_dist = self.bayesian_estimation(
                    task_duration_dist, elapsed_time
                )

            if task_info.sim_task.end <= t_c:
                print(f"   [Time: {t_c:.2f}] Elapsed: {elapsed_time:.2f}", end="")
                task_duration_dist = self.bayesian_estimation(
                    task_duration_dist, elapsed_time
                )

                print("\n-----------------------------------")
                # print(f"   [Task End] Actual End: {t_c:.2f}")
                print(f"   Planned Task Duration: {task_info.plan_task.duration:.2f}")
                print(f"   Real Task Duration: {task_info.sim_task.duration:.2f}")
                print(
                    f"   Duration updated: {task_info.plan_task.duration:.2f} -> {task_duration_dist.mean():.2f}"
                )
                print("===================================")
                break

        return t_c

    def estimate_tasks(self, plan_tasks, sim_tasks):
        start_time = 0
        for idx, (plan_task, sim_task) in enumerate(zip(plan_tasks, sim_tasks)):
            task_info = TaskInfo(idx, plan_task, sim_task, start_time)
            start_time = self.run_task(task_info)
