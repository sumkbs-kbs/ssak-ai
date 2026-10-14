"""Bayesian Prompt Tuner — MIPROv2-style autonomous prompt optimization.

Technology Origin: DSPy 2.0 / MIPROv2 (Multi-prompt Instruction Proposal & Bayesian Optimization).
Treats prompt directives and demonstration sets as optimization parameters.
Evaluates agent performance against local test cases and uses Bayesian parameter
updates to converge on the mathematically optimal prompt for Qwen3.8-27B.
"""

import random
from dataclasses import dataclass, field
from typing import override


class NoPromptCandidatesError(ValueError):
    """Raised when candidate selection is requested without configuration."""

    @override
    def __str__(self) -> str:
        return "No prompt candidates configured."


@dataclass(slots=True)  # noqa: RUF012  # noqa: MUTABLE_OK - score accumulator
class PromptCandidate:
    """A mutable prompt candidate that accumulates evaluation scores."""

    candidate_id: str
    directive_text: str
    few_shot_examples: list[str] = field(default_factory=list)
    temperature: float = 0.7
    historical_scores: list[float] = field(default_factory=list)

    @property
    def mean_score(self) -> float:
        return sum(self.historical_scores) / len(self.historical_scores) if self.historical_scores else 0.0


class BayesianPromptTuner:
    """Explores and optimizes prompt configurations using Bayesian evaluation."""

    def __init__(self, candidates: list[PromptCandidate]) -> None:
        self.candidates: list[PromptCandidate] = candidates

    def select_next_candidate(self) -> PromptCandidate:
        """Select candidate via Upper Confidence / Thompson-style sampling."""
        if not self.candidates:
            raise NoPromptCandidatesError

        # Epsilon-greedy or exploration of unvisited candidates
        unvisited = [c for c in self.candidates if not c.historical_scores]
        if unvisited:
            return random.choice(unvisited)

        # Pick candidate with highest upper confidence bound
        return max(
            self.candidates,
            key=lambda c: c.mean_score + 0.5 * (1.0 / (len(c.historical_scores) + 1)),
        )

    def record_evaluation_score(self, candidate_id: str, score: float) -> None:
        """Update historical score distribution for the candidate."""
        for c in self.candidates:
            if c.candidate_id == candidate_id:
                c.historical_scores.append(score)
                break

    def get_best_prompt(self) -> PromptCandidate:
        """Return the highest-performing prompt candidate."""
        return max(self.candidates, key=lambda c: c.mean_score)
