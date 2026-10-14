"""Pydantic request/response models for the API layer."""

from pydantic import BaseModel


class ChatMessageContent(BaseModel):
    """Chatmessagecontent.

    Bases: BaseModel
    """

    type: str
    text: str | None = None
    image_url: dict[str, str] | None = None


class ChatMessage(BaseModel):
    """Chatmessage.

    Bases: BaseModel
    """

    role: str
    content: str | list[ChatMessageContent]
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    """Chatcompletionrequest.

    Bases: BaseModel
    """

    model: str
    messages: list[ChatMessage]
    temperature: float | None = 0.7
    top_p: float | None = 1.0
    n: int | None = 1
    stream: bool | None = False
    stop: str | list[str] | None = None
    max_tokens: int | None = None
    presence_penalty: float | None = 0.0
    frequency_penalty: float | None = 0.0
    logit_bias: dict[str, float] | None = None
    user: str | None = None


class ChatCompletionResponseChoice(BaseModel):
    """Chatcompletionresponsechoice.

    Bases: BaseModel
    """

    index: int
    message: ChatMessage
    finish_reason: str | None = "stop"


class UsageStats(BaseModel):
    """Usagestats.

    Bases: BaseModel
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    """Chatcompletionresponse.

    Bases: BaseModel
    """

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionResponseChoice]
    usage: UsageStats


# Embeddings API
class EmbeddingRequest(BaseModel):
    """Embeddingrequest.

    Bases: BaseModel
    """

    input: str | list[str]
    model: str
    user: str | None = None


class EmbeddingData(BaseModel):
    """Embeddingdata.

    Bases: BaseModel
    """

    object: str = "embedding"
    embedding: list[float]
    index: int


class EmbeddingResponse(BaseModel):
    """Embeddingresponse.

    Bases: BaseModel
    """

    object: str = "list"
    data: list[EmbeddingData]
    model: str
    usage: UsageStats
