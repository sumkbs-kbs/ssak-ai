"""SSAK-AI cognitive core 계약 namespace.

P01에서 canonical record model/reference 계약만 제공한다.
저장소·adapter·runtime 연결은 P02 이후 카드가 이 namespace 안에서 추가한다.
"""

from antigravity_k.engine.cognitive import models, references
from antigravity_k.engine.cognitive.models import (
    SCHEMA_VERSION,
    CanonicalInvariantError,
    Producer,
    ProducerKind,
    Record,
    UnsupportedSchemaError,
    from_wire,
    to_wire,
)
from antigravity_k.engine.cognitive.references import (
    EntityType,
    Reference,
    ReferenceValidationError,
    ResolvedTarget,
    assert_no_supersedes_cycle,
    new_id,
    validate_references,
)

__all__ = [
    "SCHEMA_VERSION",
    "CanonicalInvariantError",
    "EntityType",
    "Producer",
    "ProducerKind",
    "Record",
    "Reference",
    "ReferenceValidationError",
    "ResolvedTarget",
    "UnsupportedSchemaError",
    "assert_no_supersedes_cycle",
    "from_wire",
    "models",
    "new_id",
    "references",
    "to_wire",
    "validate_references",
]
