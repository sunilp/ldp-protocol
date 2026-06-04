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
        """Whether a codec for this mode is available in this process.

        TEXT and SEMANTIC_FRAME ship in core and are always available.
        Richer modes (e.g. SEMANTIC_GRAPH) become available once an
        implementation registers a codec via ``register_payload_mode``.

        This is informational metadata used to decide what a party
        *advertises* — it does NOT gate negotiation. Negotiation trusts
        each party's declared preferences (see ``negotiate_payload_mode``).

        The value is process-state-dependent: ``register_payload_mode`` can
        flip a richer mode on at runtime, so do not cache this as if it were
        a constant.
        """
        return (
            self in (PayloadMode.TEXT, PayloadMode.SEMANTIC_FRAME)
            or self in _registered_modes
        )


_registered_modes: set[PayloadMode] = set()


def register_payload_mode(mode: PayloadMode) -> None:
    """Declare that a codec for ``mode`` is installed in this process.

    Built-in modes (TEXT, SEMANTIC_FRAME) are always available and need no
    registration. Richer modes — SEMANTIC_GRAPH in particular — can only be
    advertised honestly once the process actually has a codec for them. Call
    this at import/startup time from the package that provides the codec
    (e.g. flowscript-ldp registers SEMANTIC_GRAPH). A party should only
    advertise a mode it has registered, which keeps declared support honest
    instead of optimistic.

    Scope/constraints (v1): the registry is **process-wide** — every delegate
    and client in the process shares one codec registry, so registration is
    not per-instance. Call it once at import/startup, before identity cards
    are advertised or sessions negotiated; it is not designed to be called
    concurrently with active negotiation. Per-delegate codec scoping is out
    of scope for v1.
    """
    _registered_modes.add(mode)


class NegotiatedPayload(BaseModel):
    """Result of payload mode negotiation between two delegates."""

    mode: PayloadMode = PayloadMode.SEMANTIC_FRAME
    fallback_chain: list[PayloadMode] = [PayloadMode.TEXT]


def negotiate_payload_mode(
    initiator_prefs: list[PayloadMode],
    responder_prefs: list[PayloadMode],
) -> NegotiatedPayload:
    """Negotiate the best payload mode from two ordered preference lists.

    Returns the highest-preference mode declared by both parties, or
    PayloadMode.TEXT as the universal fallback.

    Negotiation trusts what each party declares it supports; it does not
    consult ``is_implemented``. Honesty of those declarations is enforced
    one layer up, at the advertising layer: a party advertises a mode only
    once it has a codec for it (see ``register_payload_mode`` and
    ``LdpIdentityCard.advertised_payload_modes``). Pass already-advertised
    preference lists in for an honest result.

    TEXT (Mode 0) is the mandatory universal floor — every LDP party can
    always speak it — so it is the result when the lists share nothing,
    even if neither list names it explicitly.
    """
    agreed = PayloadMode.TEXT
    for mode in initiator_prefs:
        if mode in responder_prefs:
            agreed = mode
            break

    # Preference lists arrive from untrusted peers and may contain duplicates;
    # build the fallback chain order-preserving but de-duplicated.
    fallback_chain: list[PayloadMode] = []
    seen: set[PayloadMode] = set()
    for mode in initiator_prefs:
        if (
            mode != agreed
            and mode not in seen
            and mode in responder_prefs
            and mode.mode_number < agreed.mode_number
        ):
            fallback_chain.append(mode)
            seen.add(mode)

    return NegotiatedPayload(mode=agreed, fallback_chain=fallback_chain)
