"""Scorer contract shared by TF-IDF and AI scorers.

A scorer does two things:
  * ``extract_keywords`` — pull salient terms (0.0–1.0) from article text.
  * ``score`` — combine those saliences with a user's learned keyword weights
    into a single *unbounded* contribution. Normalisation to 0.0–1.0 is the
    pipeline's job, not the scorer's.

The two scorers differ only in how saliences are produced; the scoring maths
(``score``) is identical, so it lives here on the base class.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScoredKeyword:
    term: str
    salience: float  # importance within the article, 0.0–1.0


class BaseScorer(ABC):
    # Short identifier persisted alongside relevance_score so the PWA can show
    # whether a score came from AI or TF-IDF (E7-S7). Override in subclasses.
    name: str = "base"

    @abstractmethod
    def extract_keywords(
        self, text: str, *, corpus: Sequence[str] | None = None
    ) -> list[ScoredKeyword]:
        """Extract keywords with salience from ``text``.

        ``corpus`` — optional sibling documents used to weight term rarity
        (IDF). Scorers that don't need it (AI) may ignore it.
        """

    def score(
        self, keywords: Sequence[ScoredKeyword], user_weights: Mapping[str, float]
    ) -> float:
        """Raw contribution: Σ salience × weight.

        Unknown keywords default to weight 0.0 — neutral, never penalising,
        so a brand-new user (no weights) scores exactly 0 on every article.
        """
        return sum(
            kw.salience * user_weights.get(kw.term, 0.0) for kw in keywords
        )
