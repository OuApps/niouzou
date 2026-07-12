"""MCP tool logic (E22-S3).

The FastMCP server (``niouzou/mcp_app.py``) owns the protocol/transport and the
tool registrations; this service owns the tool *implementations*. Every tool
runs read-only in the context of the user who owns the service account key,
delegating to the same services that back the REST API so scoring / ownership
rules can't drift. Methods return plain JSON-serialisable dicts and raise
``McpToolError`` on bad input / missing rows — FastMCP turns that into an
``isError`` tool result.
"""

import uuid

from sqlalchemy import and_, select

from niouzou.deps import SessionDep
from niouzou.models import Article, ArticleKeyword, Source
from niouzou.models.article import STATUS_ENRICHED
from niouzou.schemas.feed import FeedArticle
from niouzou.services.explore_service import ExploreService
from niouzou.services.feed_service import FeedService

# Default / max rows a listing tool returns. Kept modest so a single tool call
# doesn't dump a huge payload into the model's context.
DEFAULT_LIMIT = 10
MAX_LIMIT = 50


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


class McpService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    @staticmethod
    def _article_summary(a: FeedArticle) -> dict:
        """Compact projection of a feed/search row for a listing tool."""
        return {
            "id": str(a.id),
            "title": a.title,
            "url": a.url,
            "source": a.source.name,
            "summary": a.summary_short,
            "keywords": a.keywords,
            "score": a.smart_score if a.active_method == "smart" else a.keyword_score,
            "published_at": a.published_at.isoformat() if a.published_at else None,
        }

    async def list_feed(self, user_id: uuid.UUID, limit: int | None) -> dict:
        page = await FeedService(self.session).get_feed(
            user_id, cursor=None, limit=_clamp_limit(limit)
        )
        return {
            "articles": [self._article_summary(a) for a in page.articles],
            "count": len(page.articles),
        }

    async def search_articles(
        self, user_id: uuid.UUID, query: str, limit: int | None
    ) -> dict:
        term = (query or "").strip()
        if not term:
            raise McpToolError("`query` is required")
        page = await ExploreService(self.session).search(
            user_id, term, cursor=None, limit=_clamp_limit(limit)
        )
        return {
            "articles": [self._article_summary(a) for a in page.articles],
            "count": len(page.articles),
        }

    async def get_article(self, user_id: uuid.UUID, article_id: str) -> dict:
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
                    and_(
                        Article.id == aid,
                        Source.user_id == user_id,
                        Source.deleted_at.is_(None),
                        Article.status == STATUS_ENRICHED,
                    )
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
