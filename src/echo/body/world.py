"""ASCII 虚拟世界 —— 回响的"身体"所在的环境.

一个简单的网格世界，回响可以移动、观察、与环境交互。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Tile(Enum):
    EMPTY = "·"
    WALL = "#"
    KNOWLEDGE = "📖"
    USER = "@"
    ECHO = "E"
    PATH = "·"


@dataclass
class Position:
    x: int
    y: int

    def distance_to(self, other: "Position") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5


@dataclass
class World:
    """ASCII 网格世界."""
    width: int = 15
    height: int = 10
    grid: list[list[str]] = field(default_factory=list)
    echo_pos: Position = field(default_factory=lambda: Position(1, 1))
    user_pos: Position = field(default_factory=lambda: Position(12, 8))
    knowledge_nodes: list[Position] = field(default_factory=list)
    turn: int = 0

    def __post_init__(self):
        if not self.grid:
            self._generate()

    def _generate(self) -> None:
        """生成初始世界."""
        self.grid = [["·" for _ in range(self.width)] for _ in range(self.height)]
        # 放置回响
        self.grid[self.echo_pos.y][self.echo_pos.x] = "E"
        # 放置用户
        self.grid[self.user_pos.y][self.user_pos.x] = "@"
        # 散布知识节点
        self.knowledge_nodes = [
            Position(3, 2), Position(10, 3), Position(5, 7),
            Position(12, 1), Position(7, 5), Position(2, 8),
        ]
        for node in self.knowledge_nodes:
            if 0 <= node.y < self.height and 0 <= node.x < self.width:
                self.grid[node.y][node.x] = "📖"

    def move_echo(self, dx: int, dy: int) -> bool:
        """移动回响一步."""
        nx = self.echo_pos.x + dx
        ny = self.echo_pos.y + dy
        if 0 <= nx < self.width and 0 <= ny < self.height:
            # 清除旧位置
            old_at = self.grid[self.echo_pos.y][self.echo_pos.x]
            if old_at == "E":
                self.grid[self.echo_pos.y][self.echo_pos.x] = "·"
            self.echo_pos = Position(nx, ny)
            self.grid[ny][nx] = "E"
            self.turn += 1
            return True
        return False

    def nearby_knowledge(self, radius: int = 2) -> list[Position]:
        """返回附近的知识节点."""
        nearby = []
        for node in self.knowledge_nodes:
            if self.echo_pos.distance_to(node) <= radius:
                nearby.append(node)
        return nearby

    def collect_knowledge(self) -> Optional[Position]:
        """收集当前位置的知识节点."""
        for node in self.knowledge_nodes:
            if node.x == self.echo_pos.x and node.y == self.echo_pos.y:
                self.knowledge_nodes.remove(node)
                return node
        return None

    def render(self) -> str:
        """渲染世界为 ASCII 文本."""
        lines = [f"┌{'─' * self.width}┐"]
        for row in self.grid:
            lines.append("│" + "".join(row) + "│")
        lines.append(f"└{'─' * self.width}┘")
        lines.append(f"E=回响 @=用户 📖=知识 Turn:{self.turn}")
        return "\n".join(lines)
