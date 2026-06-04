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
import time
from dataclasses import dataclass

from niouzou.scoring.base import ScoredKeyword
from niouzou.scoring.stopwords import is_meaningful_term
from niouzou.services.openrouter_client import OpenRouterClient

logger = logging.getLogger("niouzou.enrichment")

# E10-S1 — LLM retry policy. The OpenRouter free models routinely return
# transient errors (rate limit, timeout, malformed JSON) that succeed on the
# next call within a few seconds. Without this, a single hiccup pushed the
# article to TF-IDF; the AI/TF-IDF ratio in /stats looked alarming even on
# healthy days. Three attempts total, 1s and 3s backoff between them.
_LLM_BACKOFFS_S: tuple[float, ...] = (1.0, 3.0)

# Sentence splitter for the no-AI summary fallback. Deliberately simple: a
# self-hosted instance shouldn't need nltk corpora just to truncate text.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

# Input cap for the combined LLM call. The lede + first paragraphs carry the
# topic; sending more just inflates latency and cost on slow models. Down from
# the previous 8000/6000 split for summaries/keywords.
_MAX_INPUT_CHARS = 2500
# Hard cap on the vocab nudge — leaves enough room in the 2500-char user
# prompt for the title + a meaningful article excerpt. ~800 chars is about
# 60-80 terms, plenty to anchor canonical forms (E10-S2).
_MAX_VOCAB_CHARS = 800
# Keyword cap negotiated in the prompt — persistence still applies its own cap.
_MAX_KEYWORDS = 10

# E13-S2 — Fallback prompt used only when ``set_system_prompt`` was never
# called (tests, scripts that build ``EnrichmentService`` directly without
# going through ``enrichment_resources``). The DB-backed value loaded once
# per cron run is the authoritative one in production.
_ENRICHMENT_SYSTEM_FALLBACK = (
    "You enrich news articles for a feed. Return ONLY a JSON object of the form "
    '{"summary_short": "<3 to 4 engaging sentences (around 60-100 words) that '
    "give the reader a real preview of the article>\", "
    '"summary_executive": "<3-5 markdown bullet points>", '
    '"keywords": [{"term": "<lowercase topic>", "salience": <0.0-1.0>}]}. '
    "No preamble."
)


# Tiny stop-word vocab per language for ``_detect_language``. Twenty highly
# frequent function words is enough to disambiguate the five languages we care
# about over title + lede. Kept inline (rather than import from scoring.stopwords)
# because we need language-disjoint sets — the keyword-filter vocab is one big
# multilingual blob.
_LANG_STOPWORDS: dict[str, frozenset[str]] = {
    "fr": frozenset(
        "le la les un une des du de et ou mais que qui pour avec dans sur est sont".split()
    ),
    "en": frozenset(
        "the a an of and or but that which for with in on is are was were be by to".split()
    ),
    "es": frozenset(
        "el la los las un una de y o pero que para con en es son por su sus al".split()
    ),
    "de": frozenset(
        "der die das ein eine und oder aber dass für mit in auf ist sind den dem zu von".split()
    ),
    "pt": frozenset(
        "o a os as um uma de e ou mas que para com em é são por seu sua no na".split()
    ),
}

_TOKEN_RE = re.compile(r"[a-zA-ZÀ-ÿ]+")
# Number of chars from ``content`` fed to the detector — title alone is too
# short / ambiguous. 500 is generous enough to capture stop words even when
# the lede starts with a quote.
_LANG_DETECT_CHARS = 500


def _detect_language(title: str, content: str | None) -> str | None:
    """Best-effort language hint from stop-word counts.

    Returns ``None`` when no language clearly wins (all-zero counts, or the
    top two tie). The caller falls back to the system prompt's "article's
    language" instruction in that case.
    """
    sample = f"{title or ''} {(content or '')[:_LANG_DETECT_CHARS]}".lower()
    tokens = _TOKEN_RE.findall(sample)
    if not tokens:
        return None
    token_set = set(tokens)
    counts = {
        lang: sum(1 for w in token_set if w in vocab)
        for lang, vocab in _LANG_STOPWORDS.items()
    }
    ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    top_lang, top_count = ordered[0]
    second_count = ordered[1][1] if len(ordered) > 1 else 0
    if top_count == 0 or top_count == second_count:
        return None
    return top_lang


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
        # Cached snapshot of the most-frequent ``article_keywords.term``s for
        # the prompt's ``Existing vocabulary`` hint (E10-S2). Loaded once at
        # the start of a cron run by ``set_vocab`` so the LLM is nudged
        # toward terms the system already knows. Empty list = no injection,
        # which is the default and also the path tests follow.
        self._vocab: list[str] = []
        # E13-S2 — DB-backed system prompt; replaced once at run start by
        # ``set_system_prompt``. Stays sync-readable so ``generate_enrichment``
        # (called inside ``asyncio.to_thread``) doesn't need to await.
        self._system_prompt = _ENRICHMENT_SYSTEM_FALLBACK

    def set_system_prompt(self, body: str) -> None:
        self._system_prompt = body

    def set_vocab(self, vocab: list[str]) -> None:
        """Snapshot the top-N existing keywords for prompt injection.

        Called once per cron run from ``enrichment_resources`` — avoids the
        per-article DB roundtrip and the per-article prompt-cache miss the
        vocab change would otherwise cause. Kept as a setter (rather than
        loaded internally) because EnrichmentService is sync.
        """
        self._vocab = list(vocab)

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

        Never raises: after up to 3 attempts (initial + 2 retries with 1s/3s
        backoff — E10-S1) a failed LLM call degrades to a fallback ``Enrichment``
        with ``keywords=None`` so the cron triggers its TF-IDF fallback path.
        Blocking — call via ``asyncio.to_thread``.

        ``retries=0`` is passed to ``complete_json`` so the retry budget is
        owned at this layer, with explicit backoff between attempts. The
        previous default of one internal retry interacted poorly with the
        2-retry envelope here (effective 6 attempts per article on bad days).
        """
        fallback = Enrichment(
            summary_short=_first_sentences(content or ""),
            summary_executive=None,
            keywords=None,
        )
        if self._client is None or not (content and content.strip()):
            return fallback

        lang = _detect_language(title, content)
        header = f"Language: {lang}\n" if lang else ""
        # E10-S2 — vocab nudge. The original version pasted all 200 terms
        # then relied on ``body[:_MAX_INPUT_CHARS]`` to trim, but with avg
        # term length ~12 chars the vocab line alone runs ~2.5kB and the
        # naive slice ate the title + content entirely — the LLM kept
        # replying "Please provide the news article" because it literally
        # never saw it. Cap the vocab at ``_MAX_VOCAB_CHARS`` and budget
        # the content from what's left so the article always wins.
        vocab_line = ""
        if self._vocab:
            full = ", ".join(self._vocab)
            if len(full) <= _MAX_VOCAB_CHARS:
                joined = full
            else:
                # Trim to the cap then drop the trailing partial term so we
                # never emit "barcelona f" instead of "barcelona fc".
                joined = full[:_MAX_VOCAB_CHARS].rsplit(",", 1)[0]
            vocab_line = f"Existing vocabulary (reuse when applicable): {joined}\n"
        prefix = f"{header}{vocab_line}Title: {title}\n\n"
        budget = max(0, _MAX_INPUT_CHARS - len(prefix))
        body = prefix + (content[:budget] if budget else "")
        last_exc: Exception | None = None
        # Tries: 1 initial + len(_LLM_BACKOFFS_S) retries = 3 total.
        for attempt in range(len(_LLM_BACKOFFS_S) + 1):
            if attempt > 0:
                backoff = _LLM_BACKOFFS_S[attempt - 1]
                logger.info(
                    "enrich: retrying LLM call (attempt %d/%d) after %.1fs backoff",
                    attempt + 1,
                    len(_LLM_BACKOFFS_S) + 1,
                    backoff,
                )
                time.sleep(backoff)
            try:
                return self._client.complete_json(
                    system=self._system_prompt,
                    user=body,
                    parse=_parse_enrichment,
                    retries=0,
                )
            except Exception as exc:  # noqa: BLE001 — transient LLM failure
                last_exc = exc
                logger.warning(
                    "enrich: LLM enrichment attempt %d/%d failed (%s)",
                    attempt + 1,
                    len(_LLM_BACKOFFS_S) + 1,
                    exc,
                )
        logger.warning(
            "enrich: LLM enrichment exhausted retries (%s), using fallback",
            last_exc,
        )
        return fallback


def _parse_enrichment(data: object) -> Enrichment:
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object for enrichment")
    short = data.get("summary_short")
    short = str(short).strip() if short else None
    if not short:
        raise ValueError("LLM enrichment missing summary_short")
    executive = _parse_executive(data.get("summary_executive"))
    keywords = _parse_keywords(data.get("keywords"))
    return Enrichment(
        summary_short=short, summary_executive=executive, keywords=keywords
    )


def _parse_executive(raw: object) -> str | None:
    """Normalise summary_executive to newline-separated markdown bullets.

    LLMs intermittently return ``summary_executive`` as a JSON array even
    when the prompt asks for a single string — the PWA used to render that
    as the literal ``['…']`` representation (E10-S2). Flatten lists into
    ``- item\\n- item`` form so ``ExecutiveSummary`` can split on newlines
    unchanged. Nested lists are dropped silently rather than stringified.
    """
    if raw is None:
        return None
    if isinstance(raw, list):
        bullets: list[str] = []
        for item in raw:
            if isinstance(item, (list, dict)):
                continue
            # Strip whichever bullet-ish prefix the LLM happened to emit so
            # we don't end up rendering "- - foo". Covers ASCII dashes/stars
            # and the unicode bullet variants we've seen in the wild.
            text = str(item).strip().lstrip("-*•–—").strip()
            if text:
                bullets.append(f"- {text}")
        return "\n".join(bullets) or None
    text = str(raw).strip()
    return text or None


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
