# File: core/ingredients.py
import re
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz, process

# Descriptors that don't identify the ingredient itself
_STRIP_WORDS = {
    # size/quantity qualifiers
    "large", "small", "medium", "extra", "big",
    # freshness/state
    "fresh", "dried", "frozen", "canned", "raw", "cooked", "whole",
    "organic", "unsalted", "salted", "low-sodium", "reduced-fat",
    # preparation
    "finely", "roughly", "coarsely", "thinly", "thickly", "lightly", "well",
    "chopped", "diced", "minced", "sliced", "grated", "shredded", "crushed",
    "peeled", "pitted", "trimmed", "halved", "quartered", "cubed", "zested",
    "packed", "heaping", "level", "ground", "sifted", "softened", "melted",
    # color (sometimes meaningful, but usually not for matching)
    # omitted intentionally — "black pepper" vs "white pepper" are different
}


def normalize_name(name: str) -> str:
    """Lowercase, strip prep descriptors, collapse whitespace."""
    name = name.lower().strip()
    name = re.sub(r"\(.*?\)", "", name)  # drop parenthetical notes
    words = [w for w in re.split(r"\s+", name) if w not in _STRIP_WORDS]
    return " ".join(words).strip()


def find_match(
    name: str,
    existing_names: List[str],
    high: float = 92.0,
    medium: float = 72.0,
) -> Tuple[Optional[str], float, str]:
    """
    Compare `name` against `existing_names` using fuzzy token-sort matching
    on normalized forms.

    Returns (best_existing_name, score, confidence) where confidence is one of:
      "high"   — auto-merge (score >= high)
      "medium" — ask the user (medium <= score < high)
      "none"   — treat as new ingredient
    """
    if not existing_names or not name.strip():
        return None, 0.0, "none"

    norm_input = normalize_name(name)
    norm_map: Dict[str, str] = {normalize_name(e): e for e in existing_names}

    result = process.extractOne(
        norm_input, list(norm_map.keys()), scorer=fuzz.token_sort_ratio
    )
    if result is None:
        return None, 0.0, "none"

    matched_norm, score, _ = result
    matched_original = norm_map[matched_norm]

    # Don't match a name to itself (happens when re-importing a recipe)
    if matched_original.lower() == name.strip().lower():
        return None, score, "none"

    if score >= high:
        return matched_original, score, "high"
    if score >= medium:
        return matched_original, score, "medium"
    return None, score, "none"


def resolve_lines(
    lines: List[dict],
    existing_names: List[str],
    high: float = 92.0,
    medium: float = 72.0,
) -> Tuple[List[dict], List[dict]]:
    """
    Walk import lines and fuzzy-match ingredient names against existing ones.

    Returns:
      resolved   — lines with high-confidence names already replaced;
                   each auto-merged line has an "_auto_merged_from" key
      pending    — list of medium-confidence hits for the user to review:
                   [{line_idx, original, suggested, score}, ...]
    """
    resolved: List[dict] = []
    pending: List[dict] = []

    for i, line in enumerate(lines):
        name = (line.get("ingredient") or "").strip()
        new_line = dict(line)

        if name:
            matched, score, confidence = find_match(name, existing_names, high, medium)
            if confidence == "high":
                new_line["ingredient"] = matched
                new_line["_auto_merged_from"] = name
            elif confidence == "medium":
                pending.append({
                    "line_idx": i,
                    "original": name,
                    "suggested": matched,
                    "score": round(score),
                })

        resolved.append(new_line)

    return resolved, pending
