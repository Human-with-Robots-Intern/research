import random
# 데이터 구조 및 문제 정의
subtasks = [
    {"Name": "Wash Egg", "Duration": 5, "After": None, "Interval": 0},
    {"Name": "Wash Potato", "Duration": 5, "After": "Wash Egg", "Interval": 0},
    {"Name": "Wash Tomato", "Duration": 5, "After": "Wash Potato", "Interval": 0},
    {"Name": "Prepare and Cook Fried Egg", "Duration": 10, "After": "Wash Egg", "Interval": 0},
    {"Name": "Turn off stove", "Duration": 0, "After": "Prepare and Cook Fried Egg", "Interval": 10},
]
# 적합도 계산
def calculate_fitness(schedule):
    time = 0
    end_times = {}
    penalty = 0
    for task in schedule:
        # 의존 관계 확인
        if task["After"] is not None:
            dependency_end_time = end_times.get(task["After"], -1)
            min_start_time = dependency_end_time + task["Interval"]
            if time < min_start_time:
                penalty += min_start_time - time  # 최소 대기 시간을 위반하면 페널티 부여
                time = min_start_time
        # 작업 소요 시간 추가
        time += task["Duration"]
        end_times[task["Name"]] = time
    return -penalty  # 페널티가 작을수록 높은 적합도
# 초기 인구 생성
def generate_population(subtasks, size=10):
    population = []
    for _ in range(size):
        random.shuffle(subtasks)
        population.append(subtasks[:])
    return population
# 교배
def crossover(parent1, parent2):
    point = random.randint(1, len(parent1) - 1)
    child1 = parent1[:point] + [task for task in parent2 if task not in parent1[:point]]
    child2 = parent2[:point] + [task for task in parent1 if task not in parent2[:point]]
    return child1, child2
# 돌연변이
def mutate(schedule):
    idx1, idx2 = random.sample(range(len(schedule)), 2)
    schedule[idx1], schedule[idx2] = schedule[idx2], schedule[idx1]
    return schedule
# 유전 알고리즘
def genetic_algorithm(subtasks, generations=100, population_size=10):
    population = generate_population(subtasks, size=population_size)
    for generation in range(generations):
        # 적합도 계산 및 정렬
        population = sorted(population, key=calculate_fitness, reverse=True)
        # 최적 스케줄 확인
        best_schedule = population[0]
        best_fitness = calculate_fitness(best_schedule)
        if best_fitness == 0:
            break
        # 새로운 세대 생성
        new_population = population[:2]  # 상위 2개 유지
        while len(new_population) < population_size:
            parent1, parent2 = random.sample(population[:5], 2)
            child1, child2 = crossover(parent1, parent2)
            new_population.extend([child1, child2])
        population = [mutate(schedule) if random.random() < 0.1 else schedule for schedule in new_population]
    return best_schedule
# 실행
best_schedule = genetic_algorithm(subtasks)
print("최적 스케줄:")
for task in best_schedule:
    print(task["Name"])