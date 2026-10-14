"""Self-Consistency Majority Voter — Consensus synthesis for critical decisions.

Generates or evaluates multiple candidate reasoning paths and extracts the majority
consensus, eliminating outliers and hallucinations in 27B reasoning chains.
"""

from collections import Counter
from dataclasses import dataclass


@dataclass
class CandidateHypothesis:
    """A proposed approach or solution candidate."""

    candidate_id: str
    rationale: str
    target_files: list[str]
    proposed_actions: list[str]
    confidence_score: float = 1.0


@dataclass
class ConsensusDecision:
    """The synthesized majority outcome."""

    selected_hypothesis: CandidateHypothesis
    agreement_ratio: float
    consensus_actions: list[str]
    discarded_alternatives: list[str]


class SelfConsistencyVoter:
    """Synthesizes consensus among divergent reasoning trajectories."""

    @staticmethod
    def vote_on_hypotheses(candidates: list[CandidateHypothesis]) -> ConsensusDecision | None:
        """Evaluate candidate hypotheses and select the highest-agreement option.

        Args:
            candidates: List of candidate proposals.

        Returns:
            ConsensusDecision or None if candidates is empty.
        """
        if not candidates:
            return None

        if len(candidates) == 1:
            return ConsensusDecision(
                selected_hypothesis=candidates[0],
                agreement_ratio=1.0,
                consensus_actions=candidates[0].proposed_actions,
                discarded_alternatives=[],
            )

        # Count common target files and action patterns
        file_counter: Counter[str] = Counter()
        for cand in candidates:
            for f in cand.target_files:
                file_counter[f] += 1

        # Score candidates based on agreement with the most common target files and actions
        best_candidate = candidates[0]
        max_score = -1.0

        for cand in candidates:
            score = sum(file_counter[f] for f in cand.target_files) * cand.confidence_score
            if score > max_score:
                max_score = score
                best_candidate = cand

        discarded = [c.rationale for c in candidates if c.candidate_id != best_candidate.candidate_id]
        total_votes = len(candidates)
        agree_count = sum(1 for c in candidates if any(f in c.target_files for f in best_candidate.target_files))
        ratio = agree_count / total_votes if total_votes > 0 else 1.0

        return ConsensusDecision(
            selected_hypothesis=best_candidate,
            agreement_ratio=ratio,
            consensus_actions=best_candidate.proposed_actions,
            discarded_alternatives=discarded,
        )
