"""Content extraction and summarisation for the enrichment cron (E5-S1/S2).

This service holds the cron's *business logic* so the cron module stays thin
orchestration (per docs/CONVENTIONS.md). Two responsibilities:

  * ``extract_content`` — fetch the article URL with newspaper4k, falling back
    to the RSS body when the fetch fails (paywall, block, network).
  * ``generate_enrichment`` — when AI is enabled, ask the LLM for engaging
    summaries AND salient keywords in a single combined call (E8 perf fix).
    A previous design split this into two roundtrips; combining them halves
    the OpenRouter latency per article on a slow model.

Relevance scoring lives in ``ScoringService`` (Epic 3); keyword persistence
also goes through it. The cron passes the LLM-extracted keywords to
``ScoringService.store_keywords`` to avoid re-extracting on the AI path.

All network calls here are blocking; the cron runs them off the event loop via
``asyncio.to_thread`` so the async DB session isn't starved.
"""

import logging
import re
from dataclasses import dataclass

from niouzou.scoring.base import ScoredKeyword
from niouzou.scoring.stopwords import is_meaningful_term
from niouzou.services.openrouter_client import OpenRouterClient

logger = logging.getLogger("niouzou.enrichment")

# Sentence splitter for the no-AI summary fallback. Deliberately simple: a
# self-hosted instance shouldn't need nltk corpora just to truncate text.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

# Input cap for the combined LLM call. The lede + first paragraphs carry the
# topic; sending more just inflates latency and cost on slow models. Down from
# the previous 8000/6000 split for summaries/keywords.
_MAX_INPUT_CHARS = 2500
# Keyword cap negotiated in the prompt — persistence still applies its own cap.
_MAX_KEYWORDS = 10

_ENRICHMENT_SYSTEM = (
    "You enrich news articles for a feed. Return ONLY a JSON object of the form "
    '{"summary_short": "<2 engaging sentences that make the reader want to click>", '
    '"summary_executive": "<3-5 markdown bullet points, one per line starting with \'- \'>", '
    '"keywords": [{"term": "<lowercase 1-3 word topic>", "salience": <0.0-1.0>}]}. '
    "At most 10 keywords. salience = how central the topic is (1.0 = main subject). "
    "Write in the article's language. No preamble, no commentary."
)


@dataclass(slots=True)
class ExtractedContent:
    content: str | None
    og_image_url: str | None
    # newspaper-derived fallback summary, used when AI is off or fails.
    fallback_summary: str | None


@dataclass(slots=True)
class Enrichment:
    """Combined output of the single LLM call: summaries + raw keywords.

    ``keywords`` is ``None`` when AI is disabled or the call failed — the cron
    then falls back to TF-IDF for keyword extraction. An empty list means the
    LLM ran but returned no usable keywords (kept distinct from ``None`` so
    the cron doesn't trigger fallback on a clean-but-empty reply).
    """

    summary_short: str | None
    summary_executive: str | None
    keywords: list[ScoredKeyword] | None = None


def _first_sentences(text: str, n: int = 3) -> str | None:
    """First ``n`` sentences of ``text`` — the no-AI summary_short fallback."""
    clean = " ".join(text.split())
    if not clean:
        return None
    sentences = _SENTENCE_RE.split(clean)
    return " ".join(sentences[:n]).strip() or None


class EnrichmentService:
    def __init__(self, openrouter_client: OpenRouterClient | None = None) -> None:
        # None → AI disabled; summaries come from the newspaper fallback.
        self._client = openrouter_client

    @classmethod
    def from_settings(cls) -> "EnrichmentService":
        return cls(OpenRouterClient.from_settings())

    @property
    def ai_enabled(self) -> bool:
        return self._client is not None

    def extract_content(
        self, url: str, *, rss_fallback: str | None
    ) -> ExtractedContent:
        """Fetch and parse the article; fall back to the RSS body on failure.

        Blocking (newspaper4k uses requests under the hood) — call via
        ``asyncio.to_thread`` from async code.
        """
        try:
            from newspaper import Article as NewspaperArticle

            parsed = NewspaperArticle(url)
            parsed.download()
            parsed.parse()
            text = (parsed.text or "").strip()
            if text:
                image = parsed.top_image or None
                if not image:
                    # newspaper occasionally misses og:image even when the page has
                    # one — a regex over the raw HTML is a cheap second pass.
                    image = _og_image_from_html(getattr(parsed, "html", None))
                return ExtractedContent(
                    content=text,
                    og_image_url=image,
                    fallback_summary=_first_sentences(text),
                )
            logger.info("enrich: newspaper returned empty text for %s, using RSS", url)
        except Exception as exc:  # noqa: BLE001 — any fetch/parse failure → RSS
            logger.info("enrich: content extraction failed for %s (%s), using RSS", url, exc)

        # Last resort: pull the first <img> from the RSS body. Better than nothing
        # for paywalled / blocked sources.
        return ExtractedContent(
            content=_strip_html(rss_fallback),
            og_image_url=_first_img_from_html(rss_fallback),
            fallback_summary=_first_sentences(_strip_html(rss_fallback) or ""),
        )

    def generate_enrichment(self, title: str, content: str | None) -> Enrichment:
        """One combined LLM call: summaries + keywords. Newspaper fallback otherwise.

        Never raises: a failed LLM call degrades to a fallback ``Enrichment``
        with ``keywords=None`` so the cron triggers its TF-IDF fallback path.
        Blocking — call via ``asyncio.to_thread``.
        """
        fallback = Enrichment(
            summary_short=_first_sentences(content or ""),
            summary_executive=None,
            keywords=None,
        )
        if self._client is None or not (content and content.strip()):
            return fallback

        body = f"Title: {title}\n\n{content}"
        try:
            return self._client.complete_json(
                system=_ENRICHMENT_SYSTEM,
                user=body[:_MAX_INPUT_CHARS],
                parse=_parse_enrichment,
            )
        except Exception as exc:  # noqa: BLE001 — degrade to fallback, log it
            logger.warning("enrich: LLM enrichment failed (%s), using fallback", exc)
            return fallback


def _parse_enrichment(data: object) -> Enrichment:
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object for enrichment")
    short = data.get("summary_short")
    executive = data.get("summary_executive")
    short = str(short).strip() if short else None
    executive = str(executive).strip() if executive else None
    if not short:
        raise ValueError("LLM enrichment missing summary_short")
    keywords = _parse_keywords(data.get("keywords"))
    return Enrichment(
        summary_short=short, summary_executive=executive, keywords=keywords
    )


def _parse_keywords(raw: object) -> list[ScoredKeyword]:
    """Parse the keywords array; drops malformed/stopword/duplicate entries.

    Returns ``[]`` (not ``None``) when the LLM omitted the field or returned
    nothing usable — distinct from the outer ``keywords=None`` which signals
    a transport-level failure to the cron.
    """
    if not isinstance(raw, list):
        return []
    keywords: list[ScoredKeyword] = []
    seen: set[str] = set()
    for item in raw:
        try:
            term = str(item["term"]).strip().lower()
            salience = max(0.0, min(1.0, float(item["salience"])))
        except (KeyError, TypeError, ValueError):
            continue
        if not term or term in seen or not is_meaningful_term(term):
            continue
        keywords.append(ScoredKeyword(term=term, salience=round(salience, 4)))
        seen.add(term)
        if len(keywords) >= _MAX_KEYWORDS:
            break
    return keywords


def _strip_html(html: str | None) -> str | None:
    """Crude tag strip for RSS bodies (often HTML). Enough for a summary."""
    if not html:
        return None
    text = re.sub(r"<[^>]+>", " ", html)
    text = " ".join(text.split())
    return text or None


_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_OG_IMAGE_ALT_RE = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    re.IGNORECASE,
)
_IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


def _og_image_from_html(html: str | None) -> str | None:
    """Best-effort og:image meta scrape (both attribute orderings)."""
    if not html:
        return None
    for pattern in (_OG_IMAGE_RE, _OG_IMAGE_ALT_RE):
        m = pattern.search(html)
        if m:
            return m.group(1)
    return None


def _first_img_from_html(html: str | None) -> str | None:
    """First ``<img src=...>`` URL — used as a last-resort RSS-body fallback."""
    if not html:
        return None
    m = _IMG_SRC_RE.search(html)
    return m.group(1) if m else None
