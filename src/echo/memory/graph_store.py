"""图记忆存储 —— 概念之间的关联网络.

轻量实现：优先使用 networkx（可选），回退到纯 dict 图。
用于存储和查询 "A 与 B 的关系是什么" 类型的问题。
"""

import json
from typing import Optional


class GraphStore:
    """概念图存储 —— 节点 + 边 + 权重."""

    def __init__(self):
        self._nodes: dict[str, dict] = {}    # node_id → {attrs}
        self._edges: dict[tuple, dict] = {}  # (from, to) → {attrs, weight}
        self._nx_available = False

        try:
            import networkx as nx
            self._nx = nx
            self._nx_graph = nx.DiGraph()
            self._nx_available = True
        except ImportError:
            self._nx = None
            self._nx_graph = None

    def add_node(self, node_id: str, **attrs) -> None:
        """添加概念节点."""
        self._nodes[node_id] = attrs
        if self._nx_available:
            self._nx_graph.add_node(node_id, **attrs)

    def add_edge(self, from_node: str, to_node: str,
                 relation: str = "related", weight: float = 1.0) -> None:
        """添加概念关系."""
        key = (from_node, to_node)
        if key in self._edges:
            self._edges[key]["weight"] = max(self._edges[key]["weight"], weight)
        else:
            self._edges[key] = {"relation": relation, "weight": weight}
        if self._nx_available:
            self._nx_graph.add_edge(from_node, to_node, relation=relation, weight=weight)

    def get_neighbors(self, node_id: str, max_depth: int = 1) -> list[dict]:
        """获取邻居节点."""
        neighbors = []
        for (frm, to), attrs in self._edges.items():
            if frm == node_id:
                neighbors.append({"node": to, "relation": attrs["relation"],
                                 "weight": attrs["weight"]})
            elif to == node_id:
                neighbors.append({"node": frm, "relation": attrs["relation"] + " (反向)",
                                 "weight": attrs["weight"]})
        return sorted(neighbors, key=lambda n: n["weight"], reverse=True)

    def find_path(self, from_node: str, to_node: str) -> Optional[list[str]]:
        """查找两个概念之间的最短路径."""
        if self._nx_available:
            try:
                path = self._nx.shortest_path(
                    self._nx_graph, from_node, to_node, weight="weight"
                )
                return path
            except Exception:
                return None
        # 纯 Python BFS
        return self._bfs(from_node, to_node)

    def _bfs(self, start: str, target: str) -> Optional[list[str]]:
        from collections import deque
        queue = deque([[start]])
        visited = {start}
        while queue:
            path = queue.popleft()
            node = path[-1]
            if node == target:
                return path
            for (frm, to), _ in self._edges.items():
                neighbor = None
                if frm == node and to not in visited:
                    neighbor = to
                elif to == node and frm not in visited:
                    neighbor = frm
                if neighbor:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])
        return None

    def node_count(self) -> int:
        return len(self._nodes)

    def edge_count(self) -> int:
        return len(self._edges)

    def to_dict(self) -> dict:
        return {
            "nodes": list(self._nodes.keys()),
            "edges": [(f, t, a["relation"]) for (f, t), a in self._edges.items()],
            "node_count": self.node_count(),
            "edge_count": self.edge_count(),
        }
