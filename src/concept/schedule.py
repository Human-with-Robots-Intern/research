class ScheduledTask:
    def __init__(self, name, start, end, duration, subtask=None):
        self.name = name
        self.start = start  # 시작 시간
        self.end = end  # 끝 시간
        self.duration = duration  # 지속 시간
        self.subtask = subtask  # 서브태스크 자체 정보

    def __repr__(self):
        return (
            f"ScheduledTask(name={self.name}, "
            f"subtask={self.subtask},start={self.start}, end={self.end}, duration={self.duration})"
        )
