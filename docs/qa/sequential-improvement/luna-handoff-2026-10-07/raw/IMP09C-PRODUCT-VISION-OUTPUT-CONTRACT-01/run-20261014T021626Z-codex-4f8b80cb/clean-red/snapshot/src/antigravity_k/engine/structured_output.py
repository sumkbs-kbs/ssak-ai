"""Explicit chat output contracts; schemas never resolve external references."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Literal, assert_never

from jsonschema import Draft202012Validator, SchemaError
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, ValidationError


@dataclass(frozen=True, slots=True)
class StructuredOutputError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


class TextFormat(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    type: Literal["text"]


class ObjectFormat(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    type: Literal["json_object"]


class SchemaEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    description: str | None = None
    strict: bool = False
    schema_: dict[str, JsonValue] = Field(alias="schema")


class SchemaFormat(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    type: Literal["json_schema"]
    json_schema: SchemaEnvelope


class OutputContract(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_text: str | None = None

    def native_format(self) -> str | dict[str, JsonValue]:
        if self.schema_text is None:
            return "json"
        return TypeAdapter(dict[str, JsonValue]).validate_json(self.schema_text)

    def validate_content(self, content: str) -> None:
        try:
            value = json.loads(content, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, StructuredOutputError) as exc:
            raise StructuredOutputError("Model content is not strict JSON") from exc
        if not isinstance(value, dict):
            raise StructuredOutputError("Model content must be a JSON object")
        if self.schema_text is not None:
            schema = TypeAdapter(dict[str, JsonValue]).validate_json(self.schema_text)
            if not Draft202012Validator(schema).is_valid(value):
                raise StructuredOutputError("Model content does not satisfy the requested schema")


def _reject_constant(value: str) -> None:
    raise StructuredOutputError(f"Non-JSON numeric constant: {value}")


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise StructuredOutputError("Duplicate JSON object key")
        result[key] = value
    return result


def _reject_references(value: JsonValue) -> None:
    match value:
        case dict():
            if any(key in value for key in ("$ref", "$dynamicRef", "$recursiveRef")):
                raise StructuredOutputError("Schema references are not supported")
            for key, child in value.items():
                if key in ("properties", "patternProperties", "$defs", "definitions", "dependentSchemas"):
                    if isinstance(child, dict):
                        for schema in child.values():
                            _reject_references(schema)
                if key in (
                    "items",
                    "contains",
                    "not",
                    "if",
                    "then",
                    "else",
                    "additionalProperties",
                    "propertyNames",
                    "unevaluatedProperties",
                    "unevaluatedItems",
                    "allOf",
                    "anyOf",
                    "oneOf",
                    "prefixItems",
                ):
                    _reject_references(child)
        case list():
            for child in value:
                _reject_references(child)
        case str() | int() | float() | bool() | None:
            return
        case unreachable:
            assert_never(unreachable)


def parse_output_contract[T](raw: T) -> OutputContract | None:
    if raw is None:
        return None
    try:
        parsed = TypeAdapter(
            Annotated[TextFormat | ObjectFormat | SchemaFormat, Field(discriminator="type")]
        ).validate_python(raw)
    except ValidationError as exc:
        raise StructuredOutputError("Invalid response_format envelope") from exc
    match parsed:
        case TextFormat():
            return None
        case ObjectFormat():
            return OutputContract()
        case SchemaFormat(json_schema=envelope):
            schema = envelope.schema_
            _reject_references(schema)
            if schema.get("$schema") not in (None, "https://json-schema.org/draft/2020-12/schema"):
                raise StructuredOutputError("Only JSON Schema draft 2020-12 is supported")
            if schema.get("type") != "object":
                raise StructuredOutputError("The root schema must have type object")
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as exc:
                raise StructuredOutputError("Invalid JSON Schema") from exc
            try:
                schema_text = json.dumps(schema, allow_nan=False)
            except ValueError as exc:
                raise StructuredOutputError("Schema must contain only finite JSON values") from exc
            return OutputContract(schema_text=schema_text)
        case unreachable:
            assert_never(unreachable)
