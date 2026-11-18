from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(max_length=4000)


class LlmConfig(BaseModel):
    """Cấu hình LLM hiệu lực của tenant (app gửi kèm mỗi lượt, svc-agent không lưu)."""

    provider: Literal["groq", "ollama"] = "ollama"
    groqApiKey: str = Field(default="", max_length=300)
    groqModel: str = Field(default="openai/gpt-oss-20b", max_length=120)
    groqBaseUrl: str = Field(default="", max_length=300)
    ollamaBaseUrl: str = Field(default="", max_length=300)
    assistantModel: str = Field(default="", max_length=120)
    numCtx: int = Field(default=4096, ge=256, le=32768)
    numPredict: int = Field(default=512, ge=16, le=8192)
    temperature: float = Field(default=0.2, ge=0, le=2)


class ChatContext(BaseModel):
    user: str = Field(default="", max_length=160)
    role: str = Field(default="người dùng", max_length=60)
    systemPrompt: str = Field(default="", max_length=6000, description="Prompt mặc định của app (flow để trống)")
    linkLabels: dict[str, str] = Field(default_factory=dict)


class AgentChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)
    channel: Literal["web", "mobile", "test"] | None = None
    stream: bool = True
    llm: LlmConfig = Field(default_factory=LlmConfig)
    context: ChatContext = Field(default_factory=ChatContext)
    flow: dict[str, Any] | None = Field(default=None, description="Chạy thử bản nháp (chưa lưu) thay cho flow đang hoạt động")


class SaveFlowRequest(BaseModel):
    document: dict[str, Any]
    note: str | None = Field(default=None, max_length=300)


class ValidateRequest(BaseModel):
    document: dict[str, Any]
