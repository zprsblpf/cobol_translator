from __future__ import annotations

from translator.leaf.context import LeafCtx


def translate_search(tokens: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    """Classify SEARCH leaf forms and keep them on the explicit fallback path."""
    if not tokens or tokens[0].upper() != "SEARCH":
        return [], False
    # SEARCH depends on table metadata, index state, AT END ranges, and WHEN bodies.
    # The leaf layer records this as an intentional fallback rather than guessing a loop.
    return [], False
