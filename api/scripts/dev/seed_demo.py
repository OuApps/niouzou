"""Seed a demo account with enriched articles, scores and keyword weights.

Dev/demo utility only — NOT part of the runtime. It populates enough data to
exercise the PWA end to end (Epic 4) without running Miniflux + the enrichment
cron. Everything is scoped to the demo user and re-seeded idempotently; other
users' data is never touched.

Run from the api/ dir:  uv run python -m scripts.seed_demo
"""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from niouzou.db import session_scope
from niouzou.models import (
    Article,
    ArticleFeedback,
    ArticleRelevanceScore,
    KeywordWeight,
    Source,
    User,
)
from niouzou.models.article import STATUS_ENRICHED
from niouzou.security import hash_password

DEMO_EMAIL = "demo@niouzou.app"
DEMO_PASSWORD = "demopass123"

NOW = datetime.now(timezone.utc)


def _img(seed: str) -> str:
    return f"https://images.unsplash.com/{seed}?w=800&h=400&fit=crop"


# (miniflux_feed_id, name, url)
SOURCES = [
    (9001, "The Pragmatic Engineer", "https://newsletter.pragmaticengineer.com/feed"),
    (9002, "InfoQ", "https://feed.infoq.com/"),
    (9003, "Simon Willison", "https://simonwillison.net/atom/everything/"),
]

# (source_idx, title, summary_short, summary_executive|None, og_image, hours_ago, score)
ARTICLES = [
    (
        0,
        "Why Rust is eating the world of systems programming",
        "Rust adoption has surged 40% in the last year as major tech companies migrate critical infrastructure. Memory safety without garbage collection is proving irresistible for performance-sensitive applications.",
        "- Rust adoption up 40% year-over-year in systems programming\n- Mozilla, Google, and Microsoft now ship Rust in production kernels\n- Memory safety guarantees eliminate entire classes of CVEs\n- Zero-cost abstractions mean no runtime performance penalty",
        _img("photo-1558494949-ef010cbdcc31"),
        6,
        0.94,
    ),
    (
        1,
        "The hidden costs of microservices at scale",
        "After five years of microservices, several teams are reconsidering their architecture. Network latency, debugging complexity, and operational overhead are eating into the promised benefits.",
        "- Network latency between services adds 50-200ms per request chain\n- Debugging distributed transactions requires specialized tooling\n- Several teams are migrating back to modular monoliths",
        _img("photo-1451187580459-43490279c0fa"),
        14,
        0.88,
    ),
    (
        2,
        "Building AI agents that actually work in production",
        "Most AI agent demos fail in production. This deep dive covers the patterns that survive real-world conditions: retry strategies, guardrails, and human-in-the-loop fallbacks.",
        None,
        _img("photo-1677442136019-21780ecad995"),
        28,
        0.81,
    ),
    (
        1,
        "PostgreSQL 17: the features you should actually care about",
        "PostgreSQL 17 brings incremental backups, improved JSON support, and better parallel query performance. Here is what matters for your day-to-day work and what you can safely ignore.",
        None,
        _img("photo-1544383835-bda2bc66a55d"),
        34,
        0.73,
    ),
    (
        2,
        "How we cut our AWS bill by 60% with one architectural change",
        "Moving from Lambda to long-running containers saved us $180K per year. The counter-intuitive lesson: serverless is not always cheaper at scale.",
        None,
        _img("photo-1639322537228-f710d846310a"),
        50,
        0.66,
    ),
    (
        0,
        "The TypeScript type system is Turing complete — and that is a problem",
        "TypeScript types can compute anything, which means type-checking can hang forever. Practical strategies to keep your types fast and your compiler happy.",
        None,
        _img("photo-1555066931-4365d14bab8c"),
        58,
        0.59,
    ),
    (
        2,
        "WebAssembly beyond the browser: the next five years",
        "WASM is quietly becoming the universal runtime. From edge computing to plugin systems, here is where it is heading and why you should pay attention now.",
        None,
        _img("photo-1504639725590-34d0984388bd"),
        72,
        0.51,
    ),
    (
        0,
        "Open source is broken: a maintainer manifesto",
        "After burning out maintaining a library with 50K GitHub stars, one developer shares a radical proposal for sustainable open source funding that does not rely on donations.",
        None,
        _img("photo-1522071820081-009f0129c71c"),
        90,
        0.44,
    ),
]

# (term, weight, like_count, dislike_count)
KEYWORDS = [
    ("rust", 3.6, 12, 1),
    ("ai agents", 2.1, 8, 2),
    ("postgresql", 1.8, 6, 0),
    ("performance", 1.4, 9, 3),
    ("typescript", 0.8, 5, 2),
    ("open source", 0.3, 3, 2),
    ("php", -1.8, 0, 9),
    ("blockchain", -2.5, 1, 14),
    ("nft", -3.1, 0, 11),
]


async def seed() -> None:
    async with session_scope() as session:
        # ── Demo user ──────────────────────────────────────────────────────
        user = await session.scalar(select(User).where(User.email == DEMO_EMAIL))
        if user is None:
            user = User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD))
            session.add(user)
            await session.flush()
        uid = user.id

        # ── Wipe any previous demo data (scoped strictly to this user) ──────
        await session.execute(
            text(
                "DELETE FROM article_feedbacks WHERE user_id = :uid "
                "OR article_id IN (SELECT a.id FROM articles a JOIN sources s ON s.id = a.source_id WHERE s.user_id = :uid)"
            ),
            {"uid": uid},
        )
        await session.execute(
            text("DELETE FROM article_relevance_scores WHERE user_id = :uid"),
            {"uid": uid},
        )
        await session.execute(
            text(
                "DELETE FROM article_keywords WHERE article_id IN "
                "(SELECT a.id FROM articles a JOIN sources s ON s.id = a.source_id WHERE s.user_id = :uid)"
            ),
            {"uid": uid},
        )
        await session.execute(
            text(
                "DELETE FROM article_impressions WHERE user_id = :uid "
                "OR article_id IN (SELECT a.id FROM articles a JOIN sources s ON s.id = a.source_id WHERE s.user_id = :uid)"
            ),
            {"uid": uid},
        )
        await session.execute(
            text(
                "DELETE FROM articles WHERE source_id IN "
                "(SELECT id FROM sources WHERE user_id = :uid)"
            ),
            {"uid": uid},
        )
        await session.execute(
            text("DELETE FROM keyword_weights WHERE user_id = :uid"), {"uid": uid}
        )
        await session.execute(
            text("DELETE FROM sources WHERE user_id = :uid"), {"uid": uid}
        )
        await session.flush()

        # ── Sources ─────────────────────────────────────────────────────────
        sources: list[Source] = []
        for feed_id, name, url in SOURCES:
            src = Source(user_id=uid, miniflux_feed_id=feed_id, url=url, name=name)
            session.add(src)
            sources.append(src)
        await session.flush()

        # ── Articles + per-user relevance scores ─────────────────────────────
        articles: list[Article] = []
        for i, (src_idx, title, short, execu, img, hours, score) in enumerate(ARTICLES):
            published = NOW - timedelta(hours=hours)
            art = Article(
                source_id=sources[src_idx].id,
                miniflux_entry_id=90001 + i,
                url=f"https://example.com/article-{i}",
                title=title,
                content=short,
                summary_short=short,
                summary_executive=execu,
                og_image_url=img,
                published_at=published,
                status=STATUS_ENRICHED,
                enriched_at=published + timedelta(minutes=5),
            )
            session.add(art)
            articles.append(art)
        await session.flush()

        for art, row in zip(articles, ARTICLES):
            session.add(
                ArticleRelevanceScore(article_id=art.id, user_id=uid, relevance_score=row[6])
            )

        # ── Keyword weights ──────────────────────────────────────────────────
        for term, weight, likes, dislikes in KEYWORDS:
            session.add(
                KeywordWeight(
                    user_id=uid,
                    term=term,
                    weight=weight,
                    like_count=likes,
                    dislike_count=dislikes,
                )
            )

        # ── One saved article so the Saved screen is populated ────────────────
        session.add(
            ArticleFeedback(article_id=articles[2].id, user_id=uid, action="save")
        )

    print(f"Seeded demo account:\n  email:    {DEMO_EMAIL}\n  password: {DEMO_PASSWORD}")
    print(f"  {len(SOURCES)} sources, {len(ARTICLES)} enriched articles, {len(KEYWORDS)} keywords, 1 saved")


if __name__ == "__main__":
    asyncio.run(seed())
