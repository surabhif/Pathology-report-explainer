"""Reading level estimation (Flesch-Kincaid grade level approximation).

Used to compare original report vs plain-language explanation.
Target for explanations: roughly 6th–8th grade.
"""

from __future__ import annotations

import re


def _count_syllables(word: str) -> int:
    """Rough English syllable counter — good enough for relative comparisons."""
    word = word.lower()
    word = re.sub(r"[^a-z]", "", word)
    if not word:
        return 0
    vowels = "aeiouy"
    count = 0
    prev_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def flesch_kincaid_grade(text: str) -> float:
    """Flesch-Kincaid Grade Level = 0.39*(words/sentences) + 11.8*(syllables/words) - 15.59."""
    if not text or not text.strip():
        return 0.0
    # Split sentences on ., !, ?
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    words = re.findall(r"[A-Za-z0-9']+", text)
    if not sentences or not words:
        return 0.0
    syllables = sum(_count_syllables(w) for w in words)
    n_sent = len(sentences)
    n_words = len(words)
    grade = 0.39 * (n_words / n_sent) + 11.8 * (syllables / n_words) - 15.59
    return round(max(grade, 0.0), 2)


def explanation_text_from_payload(explanation: dict) -> str:
    """Flatten explanation sentences for reading-level scoring."""
    sentences = explanation.get("sentences") or []
    return " ".join(s.get("sentence", "") for s in sentences if s.get("sentence"))
