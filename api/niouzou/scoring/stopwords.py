"""Shared stop-word filter for keyword extraction (E7-S4).

Both the TF-IDF and the AI extractor go through ``is_meaningful_term`` so a
single list governs what counts as signal. The list is intentionally small and
plain-Python — no NLTK / spaCy dependency for a self-hostable app.
"""

import re

# Covers the two languages of the current user base (FR + EN). Extend rather
# than swap in a giant generic corpus: too aggressive a filter would also drop
# legitimate short topic words.
STOPWORDS: frozenset[str] = frozenset(
    """
    a about above after again against all am an and any are aren as at
    be because been before being below between both but by can cannot could
    did do does doing don down during each few for from further
    had has have having he her here hers herself him himself his how
    i if in into is it its itself just
    me more most my myself no nor not now of off on once only or other
    ought our ours ourselves out over own same shall she should so some such
    than that the their theirs them themselves then there these they this those
    through to too under until up very was we were what when where which while
    who whom why will with would you your yours yourself yourselves
    also one two three first new news said says got get like

    le la les un une des du de d l m s t n y c j qu
    et ou mais donc or ni car que qui quoi dont où
    je tu il elle on nous vous ils elles me te se moi toi soi lui leur
    mon ma mes ton ta tes son sa ses notre nos votre vos leurs
    ce cet cette ces cela ça celui celle ceux celles
    à au aux avec sans sous sur dans par pour vers chez entre
    est sont être suis es sommes êtes ont avoir avons avez
    été étant ayant fait faire fais fait fais font
    pas plus moins très peu tout toute tous toutes
    si comme quand donc alors aussi encore déjà ici là où
    a-t-il c-est ceci celà cetait
    """.split()
)


_NUMERIC_RE = re.compile(r"^\d+([.,]\d+)?$")


def is_meaningful_term(term: str) -> bool:
    """Return False for stop words, single-character tokens, and pure numbers.

    Multi-word terms (e.g. ``"rust language"``) pass when at least one of their
    tokens is meaningful — that way an LLM-returned phrase isn't dropped just
    because it happens to contain a stop word.
    """
    term = term.strip().lower()
    if not term or len(term) < 2:
        return False
    if _NUMERIC_RE.match(term):
        return False

    tokens = term.split()
    if len(tokens) == 1:
        return tokens[0] not in STOPWORDS
    # Multi-word phrase: keep it as long as something carries signal.
    return any(
        tok not in STOPWORDS and len(tok) >= 2 and not _NUMERIC_RE.match(tok)
        for tok in tokens
    )
