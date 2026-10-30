"""Helpers shared by the demo generators: seeded randomness, topic phrasing and safe quoting."""

import hashlib
import random
import re
from collections.abc import Iterable

_ARTICLES_AND_CONJUNCTIONS = frozenset({"a", "an", "the", "and", "or", "but", "nor", "as"})
_PREPOSITION_WORDS = frozenset({"at", "by", "for", "from", "in", "into", "of", "on", "per"})
_SMALL_WORDS = _ARTICLES_AND_CONJUNCTIONS | _PREPOSITION_WORDS | {"to", "via", "vs", "with"}
# Words a subject phrase must not end with ("depth estimation for" -> "depth estimation").
_DANGLING = _SMALL_WORDS - {"but", "nor", "per"}
_DASHES = "-\N{EN DASH}\N{EM DASH}"
_FILLER = re.compile(
    r"^(?:(?:a|an|the)\s+)?(?:(?:systematic|comprehensive|literature)\s+)?"
    r"(?:(?:survey|review|study|overview|analysis)\s+(?:of|on)\s+"
    r"|research\s+(?:on|into)\s+|recent\s+(?:advances|progress)\s+in\s+"
    r"|towards?\s+|investigating\s+|exploring\s+)",
    re.IGNORECASE,
)
_YEARS = re.compile(
    r"\b(?:(?:since|after|before|from|in|between)\s+)?(?:19|20)\d{2}"
    rf"(?:\s*(?:[{_DASHES}]|to|and)\s*(?:(?:19|20)\d{{2}}|present|now|today))?\b",
    re.IGNORECASE,
)
# A topic's first clause ends at punctuation or at a spaced dash ("depth - a survey").
_CLAUSE_END = re.compile(rf"[:;.!?\n]|,|\s[{_DASHES}]\s")
_WORD = re.compile(r"\w[\w'+/&-]*")
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_\[\]$|#])")
_FALLBACK_SUBJECT = "representation learning"


def rng_for(seed: int, *parts: object) -> random.Random:
    """A random generator for one generation step, seeded from ``seed`` and ``parts``.

    The key goes through SHA-256, so seeds are stable across processes (``hash()`` is salted).
    """
    key = "\x1f".join(str(part) for part in (seed, *parts))
    digest = hashlib.sha256(key.encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))  # noqa: S311 - demo data, not secrets


def is_acronym(word: str) -> bool:
    """NYU, LiDAR, ViT, 3D, CNNs: words that keep their spelling in titles and sentences."""
    return any(char.isupper() for char in word[1:]) or any(char.isdigit() for char in word)


def subject_phrase(topic: str, max_words: int = 7) -> str:
    """The research subject of a free-form topic as a short phrase.

    "A survey of monocular depth estimation (2023-2025): transformers" becomes
    "monocular depth estimation". Topics without any words fall back to a generic subject.
    """
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", topic)
    text = _YEARS.sub(" ", text)
    text = _CLAUSE_END.split(text, maxsplit=1)[0]
    text = _FILLER.sub("", text.strip())
    words = _WORD.findall(text)[:max_words]
    while words and words[-1].lower() in _DANGLING:
        words.pop()
    if not words:
        return _FALLBACK_SUBJECT
    phrase = " ".join(words)
    # A topic typed in capitals reads as shouting in titles; acronyms survive (they have digits).
    return phrase.lower() if phrase.isupper() and len(phrase) > 5 else phrase


def title_case(phrase: str) -> str:
    """Headline capitalization that keeps acronyms ("vision transformers for NYU depth" ->
    "Vision Transformers for NYU Depth")."""
    words = []
    for index, word in enumerate(phrase.split()):
        parts = []
        for part_index, part in enumerate(word.split("-")):
            if not part or is_acronym(part):
                parts.append(part)
            elif index > 0 and part_index == 0 and part.lower() in _SMALL_WORDS:
                parts.append(part.lower())
            else:
                parts.append(part[0].upper() + part[1:].lower())
        words.append("-".join(parts))
    return " ".join(words)


def lower_phrase(phrase: str) -> str:
    """The form used inside a sentence: "Vision Transformers" -> "vision transformers"."""
    return " ".join(
        "-".join(part if is_acronym(part) else part.lower() for part in word.split("-"))
        for word in phrase.split()
    )


def sentence(text: str) -> str:
    """Capitalize the first letter only, so acronyms and names keep their spelling."""
    return text[:1].upper() + text[1:]


def article(word: str) -> str:
    """ "a" or "an" before ``word`` (by its first letter, enough for the demo vocabulary)."""
    return "an" if word[:1].lower() in "aeiou" else "a"


def counted(count: int, singular: str, plural: str) -> str:
    """ "1 paper evaluates" / "3 papers evaluate": pass both forms of the phrase."""
    return singular if count == 1 else plural


def join_words(items: Iterable[str], conjunction: str = "and") -> str:
    """ "a", "a and b", "a, b and c"."""
    values = list(items)
    if len(values) <= 2:
        return f" {conjunction} ".join(values)
    return f"{', '.join(values[:-1])} {conjunction} {values[-1]}"


def unique(items: Iterable[str]) -> list[str]:
    """Drop empty and case-insensitive duplicate strings, keeping the first spelling."""
    seen: set[str] = set()
    result = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(item.strip())
    return result


def feedback_line(feedback: str, limit: int = 280) -> str:
    """A reviewer comment as one line: whitespace collapsed, long comments shortened."""
    text = " ".join(feedback.split())
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    return text


def revision_note(feedback: str) -> str:
    """ "Revised after review: <comment>." or "" when the reviewer left no comment."""
    text = feedback_line(feedback)
    if not text:
        return ""
    return f"Revised after review: {text}" + ("" if text[-1] in ".!?" else ".")


def markdown_text(text: str) -> str:
    """Escape text quoted into a Markdown document, so a comment cannot add markup or HTML."""
    escaped = _MARKDOWN_SPECIAL.sub(r"\\\1", text)
    return escaped.replace("<", "&lt;").replace(">", "&gt;")


def code_text(text: str, limit: int = 90) -> str:
    """Text that is safe inside a generated Python docstring or comment."""
    line = " ".join(text.split()).replace("\\", "/").replace('"', "'")
    return line if len(line) <= limit else line[: limit - 3].rstrip() + "..."


def sha256_hex(*parts: str) -> str:
    """SHA-256 of the parts, each terminated by a NUL byte (so ("ab", "c") != ("a", "bc"))."""
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode())
        digest.update(b"\0")
    return digest.hexdigest()
