"""Shared, source-shaped conformance vectors for Attachment Form 1.2.

These records are test evidence, not a second form definition.  Keeping the same
responses at the differential, lifecycle, and XML boundaries prevents each layer
from quietly proving a different interpretation of the fifteen ordered slots.
"""

from __future__ import annotations

ATTACHMENT_IDS = tuple(f"{index:08d}-0000-4000-8000-{index:012d}" for index in range(1, 17))

EMPTY_RESPONSE: dict[str, str] = {}
SINGLE_RESPONSE = {"att1": ATTACHMENT_IDS[0]}
SPARSE_RESPONSE = {
    "att1": ATTACHMENT_IDS[0],
    "att5": ATTACHMENT_IDS[4],
    "att15": ATTACHMENT_IDS[14],
}
MAXIMUM_RESPONSE = {f"att{index}": ATTACHMENT_IDS[index - 1] for index in range(1, 16)}
INVALID_RESPONSE = {"att2": "not-an-attachment-id"}

# Deliberately insert the sparse fields out of source order. XML evidence must
# still serialize them as ATT1, ATT5, ATT15 according to the declarative profile.
OUT_OF_ORDER_RESPONSE = {
    "att15": ATTACHMENT_IDS[14],
    "att1": ATTACHMENT_IDS[0],
    "att5": ATTACHMENT_IDS[4],
}

REPLACEMENT_RESPONSE = {
    "att1": ATTACHMENT_IDS[15],
    "att15": ATTACHMENT_IDS[14],
}

DIFFERENTIAL_RESPONSES = (
    EMPTY_RESPONSE,
    SINGLE_RESPONSE,
    SPARSE_RESPONSE,
    MAXIMUM_RESPONSE,
    INVALID_RESPONSE,
    REPLACEMENT_RESPONSE,
)
