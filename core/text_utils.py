"""
core/text_utils.py

Shared text normalization, tokenization, and stemming utilities.
Imported by search_engine.py, bible_service.py, and build_bm25.py
to guarantee a single source of truth for tokenizer symmetry.
"""

import re
import Stemmer

# ─── Constants ────────────────────────────────────────────────────────────────

# Custom stop-words — deliberately small set to preserve theological vocabulary.
# Archaic words (thou, hath, unto, thy, ye, hast, doth, etc.) are RETAINED
# because they are semantically meaningful for Bible search.
STOP_WORDS = frozenset({"the", "is", "a", "and", "to", "of", "in", "that"})

# Regex: hyphens (‐‑‒–—―), slashes, colons → space
_PUNCTUATION_TO_SPACE = re.compile(r"[\-\u2010\u2011\u2012\u2013\u2014\u2015/:]")

# Regex: strip all remaining non-alphanumeric except spaces
_STRIP_NON_ALNUM = re.compile(r"[^a-z0-9\s]")

# Porter stemmer — module-level singleton for efficiency
STEMMER = Stemmer.Stemmer("english")

# ─── Functions ────────────────────────────────────────────────────────────────


def normalize_text(text: str) -> str:
    """Normalize a verse text for BM25 tokenization.

    This function MUST be kept symmetric across all callers
    (search_engine.py, bible_service.py, build_bm25.py).
    """
    text = text.replace("'", "").replace("\u2019", "").replace("\u2018", "")
    text = _PUNCTUATION_TO_SPACE.sub(" ", text)
    text = text.lower()
    text = _STRIP_NON_ALNUM.sub("", text)
    return " ".join(text.split())


def tokenize(text: str) -> list[str]:
    """Tokenize normalized text into words, stripping stop-words and stemming.

    Returns:
        List of stemmed tokens with stop-words removed.
    """
    normalized = normalize_text(text)
    return [STEMMER.stemWord(w) for w in normalized.split() if w not in STOP_WORDS]
