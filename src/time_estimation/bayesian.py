import numpy as np
from scipy.stats import truncnorm


def update_completion_time(mu_prior, sigma_prior, t_c):
    """
    작업 종료 시각의 사전 분포와 현재 시각을 이용하여 사후 분포를 계산

    Parameters:
    - mu_prior: 사전 분포의 평균 (초기 예상 작업 종료 시각)
    - sigma_prior: 사전 분포의 표준편차
    - t_c: 현재 시각 (작업이 완료되지 않은 시각)

    Returns:
    - mu_posterior: 사후 분포의 평균
    - sigma_posterior: 사후 분포의 표준편차
    - posterior_dist: 사후 분포 객체 (truncnorm)
    """

    # 사전 분포의 a, b 계산 (표준화)
    a, b = (t_c - mu_prior) / sigma_prior, np.inf

    # 절단 정규 분포 생성
    posterior_dist = truncnorm(a=a, b=b, loc=mu_prior, scale=sigma_prior)

    # 사후 분포의 평균과 표준편차 계산
    mu_posterior = posterior_dist.mean()
    sigma_posterior = posterior_dist.std()

    return mu_posterior, sigma_posterior, posterior_dist
