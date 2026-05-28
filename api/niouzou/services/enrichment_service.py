"""Content extraction and summarisation for the enrichment cron (E5-S1/S2).

This service holds the cron's *business logic* so the cron module stays thin
orchestration (per docs/CONVENTIONS.md). Two responsibilities:

  * ``extract_content`` — fetch the article URL with newspaper4k, falling back
    to the RSS body when the fetch fails (paywall, block, network).
  * ``generate_summaries`` — when AI is enabled, ask the LLM for an engaging
    ``summary_short`` and a bullet-point ``summary_executive``.

Keyword extraction and relevance scoring are NOT here — those go through
``ScoringService`` (the pipeline + persistence bridge from Epic 3).

All network calls here are blocking; the cron runs them off the event loop via
``asyncio.to_thread`` so the async DB session isn't starved.
"""

import logging
import re
from dataclasses import dataclass

from niouzou.services.openrouter_client import OpenRouterClient

logger = logging.getLogger("niouzou.enrichment")

# Sentence splitter for the no-AI summary fallback. Deliberately simple: a
# self-hosted instance shouldn't need nltk corpora just to truncate text.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

_SUMMARY_SYSTEM = (
    "You summarise news articles for a feed. Return ONLY a JSON object: "
    '{"summary_short": "<3 engaging sentences that make the reader want to '
    'click>", "summary_executive": "<exhaustive factual summary as markdown '
    'bullet points, one per line starting with \'- \'>"}. '
    "Write in the article's language. No preamble, no commentary."
)


@dataclass(slots=True)
class ExtractedContent:
    content: str | None
    og_image_url: str | None
    # newspaper-derived fallback summary, used when AI is off or fails.
    fallback_summary: str | None


@dataclass(slots=True)
class Summaries:
    summary_short: str | None
    summary_executive: str | None


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

    def generate_summaries(self, title: str, content: str | None) -> Summaries:
        """LLM summaries when AI is on; newspaper fallback otherwise / on failure.

        Never raises: a failed LLM call degrades to the fallback summary so the
        article is still enriched. Blocking — call via ``asyncio.to_thread``.
        """
        fallback = Summaries(_first_sentences(content or ""), None)
        if self._client is None or not (content and content.strip()):
            return fallback

        body = f"Title: {title}\n\n{content}"
        try:
            return self._client.complete_json(
                system=_SUMMARY_SYSTEM,
                user=body[:8000],
                parse=_parse_summaries,
            )
        except Exception as exc:  # noqa: BLE001 — degrade to fallback, log it
            logger.warning("enrich: LLM summary failed (%s), using fallback", exc)
            return fallback


def _parse_summaries(data: object) -> Summaries:
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object for summaries")
    short = data.get("summary_short")
    executive = data.get("summary_executive")
    short = str(short).strip() if short else None
    executive = str(executive).strip() if executive else None
    if not short:
        raise ValueError("LLM summary missing summary_short")
    return Summaries(summary_short=short, summary_executive=executive)


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
