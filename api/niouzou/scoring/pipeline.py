"""ScoringPipeline — the single entry point for scoring.

Selects the active scorer from config (AI when OPENROUTER_API_KEY is present,
TF-IDF otherwise — never both, per docs/ARCHITECTURE.md), runs it, and
normalises the raw contribution to a 0.0–1.0 ``relevance_score``.
"""

import math
from collections.abc import Mapping, Sequence

from niouzou.config import get_settings
from niouzou.scoring.base import BaseScorer, ScoredKeyword
from niouzou.scoring.tfidf import TFIDFScorer


class ScoringPipeline:
    def __init__(self, scorer: BaseScorer | None = None) -> None:
        self.scorer = scorer or self._select_scorer()

    @staticmethod
    def _select_scorer() -> BaseScorer:
        if get_settings().openrouter_api_key:
            # Imported lazily so the AI path never loads without a key.
            from niouzou.scoring.ai_keyword import AIKeywordScorer

            return AIKeywordScorer()
        return TFIDFScorer()

    @property
    def scorer_name(self) -> str:
        """Identifier of the active scorer (persisted with relevance_score)."""
        return self.scorer.name

    def extract_keywords(
        self, text: str, *, corpus: Sequence[str] | None = None
    ) -> list[ScoredKeyword]:
        return self.scorer.extract_keywords(text, corpus=corpus)

    def relevance(
        self, keywords: Sequence[ScoredKeyword], user_weights: Mapping[str, float]
    ) -> float:
        """Normalised probability (0.0–1.0) the user will enjoy the article."""
        return self._normalize(self.scorer.score(keywords, user_weights))

    @staticmethod
    def _normalize(raw: float) -> float:
        """Logistic squash of an unbounded contribution into (0, 1).

        raw = 0 → 0.5: a neutral article (or a brand-new user with no weights)
        sits at the midpoint and clears the default SCORE_THRESHOLD of 0.0, so
        new users see everything.
        """
        # Clamp before exp() so extreme weights saturate to ~0/~1 instead of
        # overflowing.
        raw = max(-60.0, min(60.0, raw))
        return 1.0 / (1.0 + math.exp(-raw))
