"""MCP tool logic (E22-S3).

The JSON-RPC transport lives in ``routers/mcp.py``; this service owns the tool
catalogue and their implementations. Every tool runs read-only in the context
of the user who owns the service account key, delegating to the same services
that back the REST API so scoring / ownership rules can't drift.
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

    Surfaced to the client as a ``tools/call`` result with ``isError: true``
    rather than a JSON-RPC protocol error, per the MCP spec.
    """


# Tool catalogue advertised by ``tools/list``. JSON Schema per the MCP spec.
TOOLS: list[dict] = [
    {
        "name": "list_feed",
        "description": (
            "Return the current personalised Niouzou feed: the top-ranked "
            "articles the user hasn't seen yet, most relevant first."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": f"How many articles (1-{MAX_LIMIT}).",
                    "minimum": 1,
                    "maximum": MAX_LIMIT,
                }
            },
        },
    },
    {
        "name": "search_articles",
        "description": (
            "Full-text search over the user's enriched articles (title and "
            "summary), newest first."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search for.",
                },
                "limit": {
                    "type": "integer",
                    "description": f"How many results (1-{MAX_LIMIT}).",
                    "minimum": 1,
                    "maximum": MAX_LIMIT,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_article",
        "description": (
            "Fetch one article by id, including its full crawled text content."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "article_id": {
                    "type": "string",
                    "description": "The article UUID.",
                }
            },
            "required": ["article_id"],
        },
    },
]


class McpService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def dispatch(
        self, user_id: uuid.UUID, name: str, arguments: dict
    ) -> dict:
        """Run a tool by name; returns a JSON-serialisable result payload."""
        if name == "list_feed":
            return await self._list_feed(user_id, arguments)
        if name == "search_articles":
            return await self._search_articles(user_id, arguments)
        if name == "get_article":
            return await self._get_article(user_id, arguments)
        raise McpToolError(f"Unknown tool: {name}")

    def _clamp_limit(self, arguments: dict) -> int:
        raw = arguments.get("limit", DEFAULT_LIMIT)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise McpToolError("`limit` must be an integer") from None
        return max(1, min(MAX_LIMIT, value))

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

    async def _list_feed(self, user_id: uuid.UUID, arguments: dict) -> dict:
        limit = self._clamp_limit(arguments)
        page = await FeedService(self.session).get_feed(
            user_id, cursor=None, limit=limit
        )
        return {
            "articles": [self._article_summary(a) for a in page.articles],
            "count": len(page.articles),
        }

    async def _search_articles(
        self, user_id: uuid.UUID, arguments: dict
    ) -> dict:
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise McpToolError("`query` is required")
        limit = self._clamp_limit(arguments)
        page = await ExploreService(self.session).search(
            user_id, query, cursor=None, limit=limit
        )
        return {
            "articles": [self._article_summary(a) for a in page.articles],
            "count": len(page.articles),
        }

    async def _get_article(self, user_id: uuid.UUID, arguments: dict) -> dict:
        raw_id = str(arguments.get("article_id", "")).strip()
        try:
            article_id = uuid.UUID(raw_id)
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
                        Article.id == article_id,
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
                .where(ArticleKeyword.article_id == article_id)
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
