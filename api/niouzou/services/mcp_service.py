"""MCP tool logic (E22-S3, re-scoped E23-S1).

The FastMCP server (``niouzou/mcp_app.py``) owns the protocol/transport and the
tool registrations; this service owns the tool *implementations*.

Since E23 the MCP is an **identity of its own**, decoupled from any user: the
tools read the whole enriched-article corpus **read-only** and never expose
scores, feedback or any per-user data. Every article projection carries a
``niouzou_url`` deep link (``{PUBLIC_APP_URL}/article/{id}``) so a Niouzou user
can open the article in the app. Methods return plain JSON-serialisable dicts
and raise ``McpToolError`` on bad input / missing rows — FastMCP turns that
into an ``isError`` tool result.
"""

import uuid

from sqlalchemy import func, or_, select

from niouzou.config import get_settings
from niouzou.deps import SessionDep
from niouzou.models import Article, ArticleKeyword, Source
from niouzou.models.article import STATUS_ENRICHED

# Default / max rows a listing tool returns. Kept modest so a single tool call
# doesn't dump a huge payload into the model's context.
DEFAULT_LIMIT = 10
MAX_LIMIT = 50
# Shorter queries are too broad to be useful; short-circuit them.
MIN_SEARCH_CHARS = 2


class McpToolError(Exception):
    """A tool-level failure (bad argument, missing article).

    FastMCP surfaces it to the client as a ``tools/call`` result with
    ``isError: true`` rather than a JSON-RPC protocol error.
    """


def _clamp_limit(limit: int | None) -> int:
    try:
        value = int(limit) if limit is not None else DEFAULT_LIMIT
    except (TypeError, ValueError):
        raise McpToolError("`limit` must be an integer") from None
    return max(1, min(MAX_LIMIT, value))


def niouzou_article_url(article_id: uuid.UUID | str) -> str:
    """Shareable Niouzou deep link for an article (E23-S2).

    ``{PUBLIC_APP_URL}/article/{id}`` when the public URL is configured,
    otherwise the path-only ``/article/{id}`` so the payload still degrades
    to something a same-origin client can resolve.
    """
    base = get_settings().public_app_url.rstrip("/")
    return f"{base}/article/{article_id}"


class McpService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    @staticmethod
    def _summary(row) -> dict:
        """Compact, score-free projection of a listing/search row."""
        return {
            "id": str(row.id),
            "title": row.title,
            "niouzou_url": niouzou_article_url(row.id),
            "url": row.url,
            "source": row.source_name,
            "summary": row.summary_short,
            "published_at": (
                row.published_at.isoformat() if row.published_at else None
            ),
        }

    def _listing_select(self):
        """Base query for the score-free listing/search tools."""
        return (
            select(
                Article.id,
                Article.title,
                Article.url,
                Article.summary_short,
                Article.published_at,
                Source.name.label("source_name"),
            )
            .join(Source, Source.id == Article.source_id)
            .where(
                Article.status == STATUS_ENRICHED,
                Source.deleted_at.is_(None),
            )
            .order_by(
                func.coalesce(Article.published_at, Article.created_at).desc(),
                Article.id.desc(),
            )
        )

    async def list_recent_articles(self, limit: int | None) -> dict:
        """Newest enriched articles across the whole base — no personalisation."""
        rows = (
            await self.session.execute(
                self._listing_select().limit(_clamp_limit(limit))
            )
        ).all()
        return {"articles": [self._summary(r) for r in rows], "count": len(rows)}

    async def search_articles(self, query: str, limit: int | None) -> dict:
        term = (query or "").strip()
        if len(term) < MIN_SEARCH_CHARS:
            raise McpToolError(
                f"`query` must be at least {MIN_SEARCH_CHARS} characters"
            )
        # Escape LIKE wildcards so '%' / '_' in user input stay literal.
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        rows = (
            await self.session.execute(
                self._listing_select()
                .where(
                    or_(
                        Article.title.ilike(pattern, escape="\\"),
                        Article.summary_executive.ilike(pattern, escape="\\"),
                    )
                )
                .limit(_clamp_limit(limit))
            )
        ).all()
        return {"articles": [self._summary(r) for r in rows], "count": len(rows)}

    async def get_article(self, article_id: str) -> dict:
        try:
            aid = uuid.UUID(str(article_id).strip())
        except ValueError:
            raise McpToolError("`article_id` must be a valid UUID") from None

        row = (
            await self.session.execute(
                select(
                    Article.id,
                    Article.title,
                    Article.url,
                    Article.summary_short,
                    Article.summary_executive,
                    Article.content,
                    Article.published_at,
                    Source.name.label("source_name"),
                )
                .join(Source, Source.id == Article.source_id)
                .where(
                    Article.id == aid,
                    Source.deleted_at.is_(None),
                    Article.status == STATUS_ENRICHED,
                )
            )
        ).first()
        if row is None:
            raise McpToolError("Article not found")

        keywords = (
            await self.session.scalars(
                select(ArticleKeyword.term)
                .where(ArticleKeyword.article_id == aid)
                .order_by(
                    ArticleKeyword.salience.desc(), ArticleKeyword.term.asc()
                )
            )
        ).all()

        return {
            "id": str(row.id),
            "title": row.title,
            "niouzou_url": niouzou_article_url(row.id),
            "url": row.url,
            "source": row.source_name,
            "summary": row.summary_short,
            "summary_executive": row.summary_executive,
            "content": row.content,
            "keywords": list(keywords),
            "published_at": (
                row.published_at.isoformat() if row.published_at else None
            ),
        }
