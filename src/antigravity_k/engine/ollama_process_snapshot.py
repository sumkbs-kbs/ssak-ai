from typing import Annotated, ClassVar

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, StrictStr, StringConstraints


class OllamaProcess(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    name: Annotated[
        StrictStr,
        StringConstraints(strip_whitespace=True, min_length=1),
        Field(validation_alias=AliasChoices("name", "model")),
    ]


class OllamaProcessSnapshot(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    models: tuple[OllamaProcess, ...]

    @property
    def names(self) -> frozenset[str]:
        return frozenset(model.name for model in self.models)
