import type { FeedArticle, ArticleDetail, SavedArticle, KeywordWeight, SourceFull } from '../types/api'

export const MOCK_ARTICLES: FeedArticle[] = [
  {
    id: '1a2b3c4d-0000-4000-8000-000000000000',
    title: 'Introducing Niouzou: The Privacy-First News Aggregator You Actually Own',
    summary_short: 'Tired of algorithmic feeds and data harvesting? Niouzou is a self-hosted news reader with AI-powered summaries that learns your interests without selling your data. Swipe right for what you love, left for what you don\'t.',
    og_image_url: 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 400"><rect width="800" height="400" fill="%230c1018"/><g transform="translate(400,200)"><text x="0" y="0" font-size="88" font-weight="900" font-family="system-ui, -apple-system, sans-serif" fill="%23ffffff" text-anchor="middle" dominant-baseline="central" letter-spacing="-2">Niouzou</text></g></svg>',
    url: 'https://github.com/OuApps/niouzou',
    source: { id: 's5', name: 'Niouzou' },
    published_at: '2026-05-27T10:00:00Z',
    relevance_score: 0.95,
    keywords: ['privacy', 'news aggregator', 'open source', 'rss', 'self-hosted'],
    read_time_minutes: 5,
  },
  {
    id: '1a2b3c4d-0001-4000-8000-000000000001',
    title: 'Why Rust is eating the world of systems programming',
    summary_short: 'Rust adoption has surged 40% in the last year as major tech companies migrate critical infrastructure. Memory safety without garbage collection is proving irresistible for performance-sensitive applications.',
    og_image_url: 'https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=800&h=400&fit=crop',
    url: 'https://example.com/rust-eating-world',
    source: { id: 's1', name: 'The Pragmatic Engineer' },
    published_at: '2026-05-26T08:30:00Z',
    relevance_score: 0.92,
    keywords: ['rust', 'systems programming', 'memory safety', 'performance'],
    read_time_minutes: 7,
  },
  {
    id: '1a2b3c4d-0002-4000-8000-000000000002',
    title: 'The hidden costs of microservices at scale',
    summary_short: 'After five years of microservices, several teams are reconsidering their architecture. Network latency, debugging complexity, and operational overhead are eating into the promised benefits.',
    og_image_url: 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=800&h=400&fit=crop',
    url: 'https://example.com/microservices-costs',
    source: { id: 's2', name: 'InfoQ' },
    published_at: '2026-05-26T06:00:00Z',
    relevance_score: 0.85,
    keywords: ['microservices', 'architecture', 'distributed systems', 'monolith'],
    read_time_minutes: 12,
  },
  {
    id: '1a2b3c4d-0003-4000-8000-000000000003',
    title: 'Building AI agents that actually work in production',
    summary_short: 'Most AI agent demos fail in production. This deep dive covers the patterns that survive real-world conditions: retry strategies, guardrails, and human-in-the-loop fallbacks.',
    og_image_url: 'https://images.unsplash.com/photo-1677442136019-21780ecad995?w=800&h=400&fit=crop',
    url: 'https://example.com/ai-agents-production',
    source: { id: 's3', name: 'Simon Willison' },
    published_at: '2026-05-25T14:00:00Z',
    relevance_score: 0.78,
    keywords: ['ai agents', 'llm', 'production', 'reliability'],
    read_time_minutes: 9,
  },
  {
    id: '1a2b3c4d-0004-4000-8000-000000000004',
    title: 'PostgreSQL 17: the features you should actually care about',
    summary_short: 'PostgreSQL 17 brings incremental backups, improved JSON support, and better parallel query performance. Here is what matters for your day-to-day work and what you can safely ignore.',
    og_image_url: 'https://images.unsplash.com/photo-1544383835-bda2bc66a55d?w=800&h=400&fit=crop',
    url: 'https://example.com/pg17-features',
    source: { id: 's4', name: 'Hacker News' },
    published_at: '2026-05-25T10:00:00Z',
    relevance_score: 0.71,
    keywords: ['postgresql', 'database', 'sql', 'performance'],
    read_time_minutes: 6,
  },
  {
    id: '1a2b3c4d-0005-4000-8000-000000000005',
    title: 'How we cut our AWS bill by 60% with one architectural change',
    summary_short: 'Moving from Lambda to long-running containers saved us $180K per year. The counter-intuitive lesson: serverless is not always cheaper at scale.',
    og_image_url: 'https://images.unsplash.com/photo-1639322537228-f710d846310a?w=800&h=400&fit=crop',
    url: 'https://example.com/aws-bill-cut',
    source: { id: 's2', name: 'InfoQ' },
    published_at: '2026-05-24T16:00:00Z',
    relevance_score: 0.65,
    keywords: ['aws', 'cloud costs', 'serverless', 'containers'],
    read_time_minutes: 8,
  },
  {
    id: '1a2b3c4d-0006-4000-8000-000000000006',
    title: 'The TypeScript type system is Turing complete — and that is a problem',
    summary_short: 'TypeScript types can compute anything, which means type-checking can hang forever. Practical strategies to keep your types fast and your compiler happy.',
    og_image_url: 'https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=800&h=400&fit=crop',
    url: 'https://example.com/typescript-turing',
    source: { id: 's3', name: 'Simon Willison' },
    published_at: '2026-05-24T09:00:00Z',
    relevance_score: 0.58,
    keywords: ['typescript', 'type system', 'compiler', 'performance'],
    read_time_minutes: 11,
  },
  {
    id: '1a2b3c4d-0007-4000-8000-000000000007',
    title: 'Open source is broken: a maintainer manifesto',
    summary_short: 'After burning out maintaining a library with 50K GitHub stars, one developer shares a radical proposal for sustainable open source funding that does not rely on donations.',
    og_image_url: 'https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=800&h=400&fit=crop',
    url: 'https://example.com/open-source-broken',
    source: { id: 's1', name: 'The Pragmatic Engineer' },
    published_at: '2026-05-23T12:00:00Z',
    relevance_score: 0.52,
    keywords: ['open source', 'sustainability', 'funding', 'burnout'],
    read_time_minutes: 15,
  },
  {
    id: '1a2b3c4d-0008-4000-8000-000000000008',
    title: 'WebAssembly beyond the browser: the next five years',
    summary_short: 'WASM is quietly becoming the universal runtime. From edge computing to plugin systems, here is where it is heading and why you should pay attention now.',
    og_image_url: 'https://images.unsplash.com/photo-1504639725590-34d0984388bd?w=800&h=400&fit=crop',
    url: 'https://example.com/wasm-future',
    source: { id: 's4', name: 'Hacker News' },
    published_at: '2026-05-23T08:00:00Z',
    relevance_score: 0.48,
    keywords: ['webassembly', 'wasm', 'edge computing', 'runtime'],
    read_time_minutes: 10,
  },
]

export function getMockArticleDetail(id: string): ArticleDetail | undefined {
  const feed = MOCK_ARTICLES.find((a) => a.id === id)
  if (!feed) return undefined
  return {
    ...feed,
    source: { ...feed.source, url: feed.url },
    summary_executive:
      id === MOCK_ARTICLES[0].id
        ? '- Self-hosted news reader: no ads, no tracking, no algorithms\n- Swipe interface learns your preferences from your reading behavior\n- TFIDFscorer + optional AI enrichment via OpenRouter\n- One-click RSS source management, supports Miniflux integration\n- Mobile-first PWA with full offline support\n- Apache 2.0 + Commons Clause: free to self-host, not to commercialize'
        : id === MOCK_ARTICLES[1].id
          ? '- Rust adoption up 40% year-over-year in systems programming\n- Mozilla, Google, and Microsoft now use Rust in production kernels\n- Memory safety guarantees eliminate entire classes of CVEs\n- Zero-cost abstractions mean no runtime performance penalty\n- Cargo ecosystem now has over 120,000 crates'
          : id === MOCK_ARTICLES[2].id
            ? '- Network latency between services adds 50-200ms per request chain\n- Debugging distributed transactions requires specialized tooling\n- Operational overhead grows linearly with service count\n- Several teams migrating back to modular monoliths\n- Key insight: start monolith, extract only when proven necessary'
            : null,
    enriched_at: '2026-05-27T10:00:00Z',
    feedback: null,
    keywords: feed.keywords,
  }
}

export const MOCK_SAVED: SavedArticle[] = [
  { ...MOCK_ARTICLES[0], saved_at: '2026-05-26T09:00:00Z' },
  { ...MOCK_ARTICLES[2], saved_at: '2026-05-25T15:30:00Z' },
  { ...MOCK_ARTICLES[4], saved_at: '2026-05-24T17:00:00Z' },
]

export const MOCK_KEYWORDS: KeywordWeight[] = [
  { term: 'rust', weight: 3.6, like_count: 12, dislike_count: 1, updated_at: '2026-05-26T08:00:00Z' },
  { term: 'ai agents', weight: 2.1, like_count: 8, dislike_count: 2, updated_at: '2026-05-25T14:00:00Z' },
  { term: 'postgresql', weight: 1.8, like_count: 6, dislike_count: 0, updated_at: '2026-05-25T10:00:00Z' },
  { term: 'performance', weight: 1.4, like_count: 9, dislike_count: 3, updated_at: '2026-05-24T16:00:00Z' },
  { term: 'typescript', weight: 0.8, like_count: 5, dislike_count: 2, updated_at: '2026-05-24T09:00:00Z' },
  { term: 'open source', weight: 0.3, like_count: 3, dislike_count: 2, updated_at: '2026-05-23T12:00:00Z' },
  { term: 'php', weight: -1.8, like_count: 0, dislike_count: 9, updated_at: '2026-05-22T08:00:00Z' },
  { term: 'blockchain', weight: -2.5, like_count: 1, dislike_count: 14, updated_at: '2026-05-21T10:00:00Z' },
  { term: 'nft', weight: -3.1, like_count: 0, dislike_count: 11, updated_at: '2026-05-20T12:00:00Z' },
]

export const MOCK_SOURCES: SourceFull[] = [
  { id: 's5', name: 'Niouzou', url: 'https://github.com/OuApps/niouzou', created_at: '2026-05-27T00:00:00Z' },
  { id: 's1', name: 'The Pragmatic Engineer', url: 'https://newsletter.pragmaticengineer.com/feed', created_at: '2026-01-01T00:00:00Z' },
  { id: 's2', name: 'InfoQ', url: 'https://feed.infoq.com/', created_at: '2026-01-15T00:00:00Z' },
  { id: 's3', name: 'Simon Willison', url: 'https://simonwillison.net/atom/everything/', created_at: '2026-02-01T00:00:00Z' },
  { id: 's4', name: 'Hacker News', url: 'https://hnrss.org/frontpage', created_at: '2026-02-15T00:00:00Z' },
]
