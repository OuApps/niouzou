"""Scoring: keyword extraction + per-user relevance scoring.

``ScoringPipeline`` is the only entry point — never call a scorer directly
(see docs/CONVENTIONS.md). It selects ``TFIDFScorer`` or ``AIKeywordScorer``
from config and normalises the raw contribution to a 0.0–1.0 relevance score.
"""

from niouzou.scoring.base import BaseScorer, ScoredKeyword
from niouzou.scoring.pipeline import ScoringPipeline
from niouzou.scoring.tfidf import TFIDFScorer

__all__ = ["BaseScorer", "ScoredKeyword", "ScoringPipeline", "TFIDFScorer"]
