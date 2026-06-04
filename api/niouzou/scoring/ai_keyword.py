"""LLM-based keyword extraction — active when OPENROUTER_API_KEY is set.

Scoring maths is inherited from BaseScorer (salience × weight); only the
extraction step differs: instead of TF-IDF, an LLM reads the article and
returns the salient terms with a 0.0–1.0 salience each.

``ScoringPipeline`` selects this scorer from config (E3); this module is E5-S3:
turning the LLM's JSON reply into ``ScoredKeyword`` objects.
"""

from collections.abc import Sequence

from niouzou.scoring.base import BaseScorer, ScoredKeyword
from niouzou.scoring.stopwords import is_meaningful_term
from niouzou.services.openrouter_client import OpenRouterClient, OpenRouterError

# Cap the article text sent to the model: the lede carries the topic, and
# free-tier context windows / costs reward brevity.
_MAX_CHARS = 6000

# E13-S2 — Fallback prompt used when ``set_system_prompt`` was never
# called. The DB-backed value loaded once per cron run from
# ``llm_prompts.scoring.ai_keywords`` overrides it in normal use.
_SYSTEM_FALLBACK = (
    "You extract the key topics from a news article. "
    "Return ONLY a JSON object of the form "
    '{"keywords": [{"term": "<lowercase topic>", "salience": <0.0-1.0>}]}. '
    "salience = how central the topic is to the article (1.0 = the main "
    "subject). Use short noun phrases (1-3 words), at most 15 keywords, "
    "no duplicates, no commentary."
)


class AIKeywordScorer(BaseScorer):
    name = "ai_keyword"

    def __init__(
        self,
        client: OpenRouterClient | None = None,
        *,
        max_keywords: int = 15,
        retries: int = 1,
    ) -> None:
        # Lazily resolved so importing this module never requires a key; a
        # client can also be injected (tests pass a fake — never the real API).
        self._client = client
        self._max_keywords = max_keywords
        self._retries = retries
        # E13-S2 — replaced once per run by ``set_system_prompt``.
        self._system_prompt = _SYSTEM_FALLBACK

    def set_system_prompt(self, body: str) -> None:
        self._system_prompt = body

    def _get_client(self) -> OpenRouterClient:
        if self._client is None:
            client = OpenRouterClient.from_settings()
            if client is None:
                raise OpenRouterError(
                    "AIKeywordScorer requires OPENROUTER_API_KEY to be set"
                )
            self._client = client
        return self._client

    def extract_keywords(
        self, text: str, *, corpus: Sequence[str] | None = None
    ) -> list[ScoredKeyword]:
        """Ask the LLM for salient keywords and parse them.

        ``corpus`` is ignored — unlike TF-IDF, the LLM judges salience from the
        article alone. Raises ``OpenRouterError`` if the model never returns a
        usable reply (the cron then falls back to TF-IDF).
        """
        if not text or not text.strip():
            return []

        return self._get_client().complete_json(
            system=self._system_prompt,
            user=text[:_MAX_CHARS],
            parse=self._parse,
            retries=self._retries,
        )

    def _parse(self, data: object) -> list[ScoredKeyword]:
        """Turn the LLM JSON into deduped, salience-clamped ScoredKeywords."""
        items = data["keywords"] if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise ValueError(f"Expected a list of keywords, got {type(items).__name__}")

        keywords: list[ScoredKeyword] = []
        seen: set[str] = set()
        for item in items:
            try:
                term = str(item["term"]).strip().lower()
                # Clamp into [0, 1] so a chatty model can't violate the salience
                # CHECK constraint on article_keywords.
                salience = max(0.0, min(1.0, float(item["salience"])))
            except (KeyError, TypeError, ValueError):
                # Skip one malformed item rather than discarding the whole reply.
                continue
            if not term or term in seen:
                continue
            if not is_meaningful_term(term):
                # Drop stop words, single chars, and pure numbers — the LLM
                # occasionally returns "de", "the", "2024" etc.
                continue
            keywords.append(ScoredKeyword(term=term, salience=round(salience, 4)))
            seen.add(term)
            if len(keywords) >= self._max_keywords:
                break

        if not keywords:
            raise ValueError("LLM returned no usable keywords")
        return keywords
