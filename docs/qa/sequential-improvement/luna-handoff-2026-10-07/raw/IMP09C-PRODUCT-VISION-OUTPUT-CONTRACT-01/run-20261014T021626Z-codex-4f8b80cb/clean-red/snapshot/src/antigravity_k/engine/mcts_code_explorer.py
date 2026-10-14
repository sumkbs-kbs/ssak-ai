"""MCTS Code Tree Explorer — Monte Carlo Tree Search for software engineering.

Technology Origin: SWE-Search / QwQ-Reasoning MCTS Architecture (2025-2026).
Explores candidate code patch trajectories as a search tree:
- Selection: UCB1 (Upper Confidence Bound) node selection
- Expansion: Branching candidate modifications
- Rollout Heuristic: Fast AST parse + Linter score evaluation
- Backpropagation: Value updates across trajectory nodes
"""

import math
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class MCTSNode:
    """A node in the code modification search tree."""

    node_id: str
    patch_description: str
    parent: "MCTSNode | None" = None
    children: list["MCTSNode"] = field(default_factory=list)
    visits: int = 0
    value: float = 0.0
    is_terminal: bool = False
    code_state: str = ""

    def ucb1_score(self, total_parent_visits: int, c_param: float = 1.414) -> float:
        """Compute Upper Confidence Bound 1 for node exploration vs exploitation."""
        if self.visits == 0:
            return float("inf")
        exploitation = self.value / self.visits
        exploration = c_param * math.sqrt(math.log(total_parent_visits) / self.visits)
        return exploitation + exploration


class MCTSCodeExplorer:
    """Explores branching code solutions using Monte Carlo Tree Search."""

    def __init__(self, root_state: str, max_iterations: int = 10) -> None:
        self.root: MCTSNode = MCTSNode(node_id="root", patch_description="Initial State", code_state=root_state)
        self.max_iterations: int = max_iterations

    def search_best_trajectory(
        self,
        expand_fn: Callable[[MCTSNode], list[tuple[str, str, str]]],
        eval_heuristic_fn: Callable[[str], float],
    ) -> MCTSNode:
        """Run MCTS iterations to find the highest-value code patch trajectory.

        Args:
            expand_fn: Callable(node) -> list of (child_id, patch_desc, new_code)
            eval_heuristic_fn: Callable(code_state) -> float score [0.0 ~ 1.0]

        Returns:
            The highest-value MCTSNode.
        """
        for _ in range(self.max_iterations):
            # 1. Selection
            node = self._select(self.root)

            # 2. Expansion
            if not node.is_terminal and node.visits > 0:
                child_candidates = expand_fn(node)
                for c_id, desc, code in child_candidates:
                    child_node = MCTSNode(
                        node_id=f"{node.node_id}_{c_id}",
                        patch_description=desc,
                        parent=node,
                        code_state=code,
                    )
                    node.children.append(child_node)
                if node.children:
                    node = node.children[0]

            # 3. Rollout / Evaluation
            rollout_score = eval_heuristic_fn(node.code_state)

            # 4. Backpropagation
            self._backpropagate(node, rollout_score)

        # Return best child of root
        if not self.root.children:
            return self.root
        return max(self.root.children, key=lambda c: c.visits)

    def _select(self, node: MCTSNode) -> MCTSNode:
        while node.children:
            node = max(node.children, key=lambda c: c.ucb1_score(max(node.visits, 1)))
        return node

    def _backpropagate(self, node: MCTSNode | None, value: float) -> None:
        curr = node
        while curr:
            curr.visits += 1
            curr.value += value
            curr = curr.parent
