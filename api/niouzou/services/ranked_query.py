"""SQL helpers shared by FeedService and ExploreService.

Both services rank articles by ``feed_rank`` (HN-style gravity formula) and
project the same row shape — these constants and helpers were extracted out
of ``feed_service`` so the dependency between the two services is explicit
and the names don't have to live behind a leading underscore.

E16-S9 — ``scoring_mode`` selects the *active* score column (``keyword_score``
or ``smart_score``) that drives BOTH the threshold filter and the gravity
ranking; the projection always returns both scores (+ cold flags) so the PWA
can render the two chips side by side (E16-S10). An active score that is NULL
(method had no input for this row) is treated exactly like cold-start:
baseline 0.5 in the rank, threshold bypassed — the article surfaces instead
of being hidden.
"""

from sqlalchemy import text

from niouzou.models.article import STATUS_ENRICHED
from niouzou.schemas.feed import FeedArticle, SourceRef

DEFAULT_LIMIT = 20
MAX_LIMIT = 50

# Whitelist mapping scoring_mode → (score column, cold flag column). The mode
# string never reaches the SQL directly — unknown values fall back to the
# keyword column, so there is no injection surface.
_ACTIVE_COLUMNS: dict[str, tuple[str, str]] = {
    "keyword": ("ars.keyword_score", "ars.keyword_cold_start"),
    "smart": ("ars.smart_score", "ars.smart_cold_start"),
}


def active_columns(scoring_mode: str) -> tuple[str, str]:
    """(score, cold flag) SQL refs for the active method — whitelisted."""
    return _ACTIVE_COLUMNS.get(scoring_mode, _ACTIVE_COLUMNS["keyword"])


def feed_rank_sql(scoring_mode: str) -> str:
    """feed_rank, computed once and reused in SELECT, ORDER BY and the keyset
    filter.

    Cold-start articles (E10-S4) — and rows whose active score is NULL
    (E16-S9) — use a synthetic 0.5 baseline so they sort between bona-fide
    good and bad articles instead of clumping at whatever neutral value the
    scorer happened to emit.
    """
    score, cold = active_columns(scoring_mode)
    return (
        f"(CASE WHEN {cold} OR {score} IS NULL THEN 0.5 ELSE {score} END)"
        " / power("
        "GREATEST(EXTRACT(EPOCH FROM (now() - COALESCE(a.published_at, a.created_at)))"
        "/ 3600.0, 0) + 2, :gravity)"
    )


def ranked_columns(scoring_mode: str) -> str:
    """Projection shared by /feed and /explore/new. Aliased so the outer
    SELECT can keyset on (feed_rank, id) without recomputing the rank."""
    return f"""
    a.id AS id,
    a.title AS title,
    a.summary_short AS summary_short,
    a.summary_executive AS summary_executive,
    a.content AS content,
    a.og_image_url AS og_image_url,
    a.url AS url,
    a.published_at AS published_at,
    s.id AS source_id,
    s.name AS source_name,
    ars.keyword_score AS keyword_score,
    ars.keyword_cold_start AS keyword_cold_start,
    ars.smart_score AS smart_score,
    ars.smart_cold_start AS smart_cold_start,
    a.enrichment_model AS enrichment_model,
    (a.content IS NOT NULL
     AND char_length(a.content) < :premium_max_chars
    ) AS is_premium,
    COALESCE(fb.reaction, 'none') AS reaction,
    COALESCE(fb.is_saved, false) AS is_saved,
    COALESCE(fb.read_full_article, false) AS read_full_article,
    {feed_rank_sql(scoring_mode)} AS feed_rank,
    COALESCE(
        (SELECT array_agg(ak.term ORDER BY ak.salience DESC, ak.term ASC)
         FROM article_keywords ak WHERE ak.article_id = a.id),
        ARRAY[]::text[]
    ) AS keywords
"""


FROM_JOINS = """
FROM articles a
JOIN sources s ON s.id = a.source_id
JOIN article_relevance_scores ars
    ON ars.article_id = a.id AND ars.user_id = :user_id
LEFT JOIN article_impressions ai
    ON ai.article_id = a.id AND ai.user_id = :user_id
LEFT JOIN article_feedbacks fb
    ON fb.article_id = a.id AND fb.user_id = :user_id
"""


def build_ranked_query(
    *,
    scoring_mode: str,
    apply_threshold: bool,
    apply_random_surface: bool,
    keyset: str = "",
    impression_exclusion: str = "AND ai.article_id IS NULL",
    extra_filters: str = "",
) -> text:
    """Assemble the ranked SELECT used by /feed and /explore/new.

    Args:
        scoring_mode: which persisted score drives the filter + ranking
            (E16-S9). Read once per request from the effective settings.
        apply_threshold: keep the ``active_score >= :threshold`` filter.
        apply_random_surface: enable the random-surface escape hatch.
        keyset: extra ``AND (feed_rank, id) < (:cursor_rank, :cursor_id)``
            predicate, or empty string for the first page.
        impression_exclusion: overridable so /feed?start=:id can let one
            already-impressed article through.
        extra_filters: caller-supplied ``AND ...`` predicates injected into
            the inner WHERE (E11-S1: per-request ``min_score`` and
            ``source_ids`` on /explore/new).
    """
    score, cold = active_columns(scoring_mode)
    # Cold-start articles (E10-S4) — and NULL active scores (E16-S9) — bypass
    # the score threshold unconditionally: they're the only chance for the
    # user to ever feedback unfamiliar content. The random-surface escape
    # hatch keeps its independent role (broad exploration over already-warm
    # articles).
    bypass = f"OR {cold} = TRUE OR {score} IS NULL"
    score_filter = ""
    if apply_threshold and apply_random_surface:
        score_filter = (
            f"AND ({score} >= :threshold {bypass} OR random() < :random_rate)"
        )
    elif apply_threshold:
        score_filter = f"AND ({score} >= :threshold {bypass})"
    elif apply_random_surface:
        score_filter = "AND random() < :random_rate"
    # else: no score gate at all (Explore New).

    return text(
        f"""
        WITH ranked AS (
            SELECT
                {ranked_columns(scoring_mode)}
            {FROM_JOINS}
            WHERE s.user_id = :user_id
                AND s.deleted_at IS NULL
                AND a.status = '{STATUS_ENRICHED}'
                {impression_exclusion}
                {score_filter}
                {extra_filters}
        )
        SELECT * FROM ranked
        WHERE true {keyset}
        ORDER BY feed_rank DESC, id DESC
        LIMIT :limit
        """
    )


def row_to_article(row, active_method: str) -> FeedArticle:
    """Map a ranked-query result mapping into the public FeedArticle schema."""
    return FeedArticle(
        id=row["id"],
        title=row["title"],
        summary_short=row["summary_short"],
        summary_executive=row["summary_executive"],
        content=row["content"],
        og_image_url=row["og_image_url"],
        url=row["url"],
        source=SourceRef(id=row["source_id"], name=row["source_name"]),
        published_at=row["published_at"],
        keyword_score=row["keyword_score"],
        keyword_cold_start=bool(row["keyword_cold_start"]),
        smart_score=row["smart_score"],
        smart_cold_start=bool(row["smart_cold_start"]),
        active_method=active_method,
        enrichment_model=row["enrichment_model"],
        keywords=list(row["keywords"] or []),
        is_premium=bool(row["is_premium"]),
        reaction=row["reaction"],
        is_saved=bool(row["is_saved"]),
        read_full_article=bool(row["read_full_article"]),
    )


def clamp_limit(limit: int | None) -> int:
    """Clamp a user-supplied page size to the configured range."""
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(limit, MAX_LIMIT))
