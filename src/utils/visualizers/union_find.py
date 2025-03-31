# utils/viz/union_find.py
from collections import defaultdict


class UnionFind:
    """
    Disjoint Set(Union-Find) 자료구조.
    여러 그룹을 병합하거나, 루트를 찾아 그룹화할 때 사용.
    """

    def __init__(self):
        self.parent = {}
        self.rank = {}

    def find(self, x):
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x, y):
        rx = self.find(x)
        ry = self.find(y)
        if rx != ry:
            if self.rank[rx] > self.rank[ry]:
                self.parent[ry] = rx
            elif self.rank[rx] < self.rank[ry]:
                self.parent[rx] = ry
            else:
                self.parent[ry] = rx
                self.rank[rx] += 1

    def add(self, x):
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0


def merge_groups(groups):
    """
    여러 dependency 그룹(리스트 형태)을 받아 Union-Find로 병합해,
    최종적으로 묶인 그룹 리스트를 반환한다.
    예:
      groups = [
        ["A","B"],
        ["B","C"],
        ["D","E"],
      ]
      => 결과적으로 A,B,C / D,E 두 그룹
    """
    uf = UnionFind()
    # 모든 요소를 UnionFind에 추가
    for group in groups:
        for item in group:
            uf.add(item)

    # 그룹 내 첫 요소 기준 union
    for group in groups:
        for i in range(1, len(group)):
            uf.union(group[0], group[i])

    # 그룹화 결과
    merged = defaultdict(set)
    for item in uf.parent:
        root = uf.find(item)
        merged[root].add(item)

    # set -> list, 정렬
    return [sorted(list(g)) for g in merged.values()]
