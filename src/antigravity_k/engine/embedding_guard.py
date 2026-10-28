"""No-substitute embedding policy (r29).

Vector stores may only embed through an explicitly approved binding (e.g. nomic-embed-text via the
installed Ollama). Chroma's implicit default embedding function (ONNX all-MiniLM, downloaded on first
use) and any other substitute model are never used; callers get an explicit not-ready error instead
of an empty result that looks like success.
"""

from __future__ import annotations

NO_BINDING_REASON = "no approved embedding binding (Chroma default ONNX and substitute embeddings are disabled)"


class EmbeddingNotReadyError(RuntimeError):
    """Raised when a vector operation needs an embedding but no approved binding exists."""

    def __init__(self, where: str) -> None:
        super().__init__(f"{where}: {NO_BINDING_REASON}")
        self.where = where
