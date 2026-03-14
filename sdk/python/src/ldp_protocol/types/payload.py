"""LDP payload mode definitions and negotiation."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class PayloadMode(str, Enum):
    """Payload mode for LDP message exchange."""

    TEXT = "text"
    SEMANTIC_FRAME = "semantic_frame"
    EMBEDDING_HINTS = "embedding_hints"
    SEMANTIC_GRAPH = "semantic_graph"

    @property
    def mode_number(self) -> int:
        return {
            PayloadMode.TEXT: 0,
            PayloadMode.SEMANTIC_FRAME: 1,
            PayloadMode.EMBEDDING_HINTS: 2,
            PayloadMode.SEMANTIC_GRAPH: 3,
        }[self]

    @property
    def is_implemented(self) -> bool:
        return self in (PayloadMode.TEXT, PayloadMode.SEMANTIC_FRAME)


class NegotiatedPayload(BaseModel):
    """Result of payload mode negotiation between two delegates."""

    mode: PayloadMode = PayloadMode.SEMANTIC_FRAME
    fallback_chain: list[PayloadMode] = [PayloadMode.TEXT]


def negotiate_payload_mode(
    initiator_prefs: list[PayloadMode],
    responder_prefs: list[PayloadMode],
) -> NegotiatedPayload:
    """Negotiate the best payload mode from two ordered preference lists.

    Returns the highest-preference mode supported by both parties,
    or PayloadMode.TEXT as the universal fallback.
    """
    agreed = PayloadMode.TEXT
    for mode in initiator_prefs:
        if mode.is_implemented and mode in responder_prefs:
            agreed = mode
            break

    fallback_chain = [
        mode
        for mode in initiator_prefs
        if mode.is_implemented
        and mode != agreed
        and mode in responder_prefs
        and mode.mode_number < agreed.mode_number
    ]

    return NegotiatedPayload(mode=agreed, fallback_chain=fallback_chain)
