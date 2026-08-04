#!/usr/bin/env python3
"""chunk_id helpers — doc and code_anchor share the same suffix format."""

from __future__ import annotations


def chunk_id_for(doc_id: str, index: int = 0) -> str:
    """Build chunk_id. Anchor doc_id may already contain '#{symbol}'."""
    return f"{doc_id}#{index}"


def parse_chunk_id(chunk_id: str) -> tuple[str, str]:
    """
    Split chunk_id into (doc_id, chunk_index).

    Uses rsplit('#', 1) so anchor doc_ids like
    anchor:billing-api:.../SubscriptionController.java#SubscriptionController
    are not broken on the inner '#'.
    """
    if "#" not in chunk_id:
        return chunk_id, "0"
    doc_id, chunk_index = chunk_id.rsplit("#", 1)
    return doc_id, chunk_index
