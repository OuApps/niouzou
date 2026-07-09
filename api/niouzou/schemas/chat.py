"""Article chat schemas (E21-S2).

The conversation is ephemeral in v1: the client re-sends the whole thread on
every turn, so the request carries the full message history and the server
holds no state. Bounds are enforced here (Pydantic → 422 with the standard
error envelope) so ``ChatService`` can assume a sane payload.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Hard bounds on the client-supplied thread. Generous for a human
# conversation, tight enough that a runaway client can't ship megabytes of
# prompt to OpenRouter on our bill.
MAX_MESSAGES = 40
MAX_MESSAGE_CHARS = 4_000
MAX_THREAD_CHARS = 24_000


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_MESSAGES)

    @model_validator(mode="after")
    def _validate_thread(self) -> "ChatRequest":
        if self.messages[-1].role != "user":
            raise ValueError("last message must be a user turn")
        total = sum(len(m.content) for m in self.messages)
        if total > MAX_THREAD_CHARS:
            raise ValueError(
                f"thread too long ({total} chars > {MAX_THREAD_CHARS})"
            )
        return self
