"""LLM-based keyword extraction — active when OPENROUTER_API_KEY is set.

Scoring maths is inherited from BaseScorer (salience × weight); only the
extraction step differs. The extraction itself is implemented in Epic 5
(E5-S3); here it exists so ScoringPipeline can select it from config today.
"""

from collections.abc import Sequence

from niouzou.scoring.base import BaseScorer, ScoredKeyword


class AIKeywordScorer(BaseScorer):
    def extract_keywords(
        self, text: str, *, corpus: Sequence[str] | None = None
    ) -> list[ScoredKeyword]:
        raise NotImplementedError(
            "LLM keyword extraction is implemented in Epic 5 (E5-S3)"
        )
