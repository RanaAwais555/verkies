"""UUIDv7 identifiers: time-ordered, so primary-key indexes stay compact and rows sort by age."""

import os
import threading
import time
import uuid

_RAND_A_BITS = 12
_RAND_B_BITS = 62
_lock = threading.Lock()
_last = 0


def uuid7() -> uuid.UUID:
    """RFC 9562 version 7 UUID (48-bit Unix milliseconds, 74 random bits).

    Strictly increasing within a process (RFC 9562 §6.2): an ID made in the same millisecond
    as the previous one is the previous one plus one, so rows written together (for example
    the timeline events of one approval) keep their creation order.
    """
    global _last
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
    with _lock:
        if value <= _last:
            value = _last + 1  # 62 random bits of headroom; overflow is not a practical concern
        _last = value
    return uuid.UUID(int=value)
