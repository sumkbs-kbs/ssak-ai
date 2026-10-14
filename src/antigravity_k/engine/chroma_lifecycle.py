"""Serialize Chroma client acquisition/release around its shared system registry."""

from threading import RLock
from typing import Final

# Chroma publishes a new shared System before its native bindings finish starting.
CHROMA_LIFECYCLE_LOCK: Final = RLock()
