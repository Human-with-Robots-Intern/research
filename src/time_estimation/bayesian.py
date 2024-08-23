import numpy as np
import scipy.stats as stats


class BayesianSubtaskTimeEstimator:
    def __init__(self, prior_mean, prior_std, initial_data=None):
        # Initial prior mean and standard deviation (assuming normal distribution)
        self.prior_mean = prior_mean
        self.prior_std = prior_std
        self.prior_variance = prior_std**2

        if initial_data is not None:
            self.update_posterior(initial_data)
        else:
            self.posterior_mean = self.prior_mean
            self.posterior_variance = self.prior_variance

    def update_posterior(self, observed_times):
        """
        Update the posterior mean and variance based on observed data (Bayesian update).
        observed_times: List of observed durations for the subtask.
        """
        observed_times = np.array(observed_times)
        n = len(observed_times)
        sample_mean = observed_times.mean()
        sample_variance = observed_times.var(ddof=1)

        # Update posterior mean and variance using Bayesian updating for normal distribution
        self.posterior_variance = 1 / (1 / self.prior_variance + n / sample_variance)
        self.posterior_mean = self.posterior_variance * (
            self.prior_mean / self.prior_variance + n * sample_mean / sample_variance
        )

    def predict_time(self):
        """
        Predict the time for the next subtask execution.
        Returns the mean of the posterior distribution as the predicted time.
        """
        return self.posterior_mean

    def predict_time_with_uncertainty(self, confidence_level=0.95):
        """
        Predict the time with uncertainty (confidence interval).
        confidence_level: The desired confidence level for the interval.
        Returns the mean and the confidence interval of the posterior distribution.
        """
        z_score = stats.norm.ppf(1 - (1 - confidence_level) / 2)
        confidence_interval = z_score * np.sqrt(self.posterior_variance)
        return self.posterior_mean, (
            self.posterior_mean - confidence_interval,
            self.posterior_mean + confidence_interval,
        )


# Example usage
if __name__ == "__main__":
    # Initialize the estimator with a prior mean of 5 minutes and a standard deviation of 2 minutes
    estimator = BayesianSubtaskTimeEstimator(prior_mean=5, prior_std=2)

    # Simulate observing times for a subtask (e.g., the robot performs the subtask multiple times)
    observed_times = [6, 7, 5, 6.5, 6]

    # Update the estimator with the observed times
    estimator.update_posterior(observed_times)

    # Predict the time for the next subtask
    predicted_time = estimator.predict_time()
    print(f"Predicted time for the next subtask: {predicted_time:.2f} minutes")

    # Predict time with uncertainty
    predicted_time, confidence_interval = estimator.predict_time_with_uncertainty(
        confidence_level=0.95
    )
    print(
        f"Predicted time: {predicted_time:.2f} minutes, 95% confidence interval: {confidence_interval[0]:.2f} - {confidence_interval[1]:.2f} minutes"
    )
