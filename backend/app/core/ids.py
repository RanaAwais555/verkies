"""UUIDv7 identifiers: time-ordered, so primary-key indexes stay compact and rows sort by age."""

import os
import time
import uuid

_RAND_A_BITS = 12
_RAND_B_BITS = 62


def uuid7() -> uuid.UUID:
    """RFC 9562 version 7 UUID (48-bit Unix milliseconds, 74 random bits)."""
    millis = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    rand_a = rand >> (80 - _RAND_A_BITS)
    rand_b = rand & ((1 << _RAND_B_BITS) - 1)
    value = (
        (millis & ((1 << 48) - 1)) << 80
        | 0x7 << 76  # version
        | rand_a << 64
        | 0b10 << 62  # RFC 4122 variant
        | rand_b
    )
    return uuid.UUID(int=value)
