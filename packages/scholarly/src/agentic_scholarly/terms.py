"""Query terms: the words of a query or title that say what a paper is about."""

import re
from typing import Final

# Function words, plus words that only narrow a search without naming a topic.
STOPWORDS: Final = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "based",
        "be",
        "by",
        "for",
        "from",
        "how",
        "in",
        "into",
        "is",
        "it",
        "its",
        "new",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "this",
        "to",
        "toward",
        "towards",
        "using",
        "via",
        "what",
        "when",
        "which",
        "with",
    }
)
_TOKEN: Final = re.compile(r"[^\W_]+")


def terms(text: str, *, keep_stopwords: bool = False) -> list[str]:
    """Lowercase words of two or more characters, in order and unique, without stopwords
    unless asked."""
    words = (word for word in _TOKEN.findall(text.casefold()) if len(word) > 1)
    return list(dict.fromkeys(w for w in words if keep_stopwords or w not in STOPWORDS))


def stem(word: str) -> str:
    """A light plural strip (networks to network), applied to both sides of a comparison."""
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def stems(text: str) -> set[str]:
    return {stem(word) for word in terms(text)}
