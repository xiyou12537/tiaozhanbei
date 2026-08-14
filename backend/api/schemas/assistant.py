from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AssistantSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=160)


class AssistantSessionResponse(BaseModel):
    session_id: str
    title: str | None
    created_at: str
    updated_at: str
    messages: list["AssistantMessageResponse"] = Field(default_factory=list)
    tool_executions: list["AssistantToolExecutionResponse"] = Field(default_factory=list)


class AssistantMessageResponse(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: str


class AssistantToolExecutionResponse(BaseModel):
    execution_id: str
    tool_name: str
    tool_kind: Literal["read", "draft"]
    status: str
    parameter_summary: str
    confirmation_id: str | None = None
    confirmation_expires_at: str | None = None
    result: dict[str, Any] | None = None


class AssistantStreamMessageRequest(BaseModel):
    """Plain chat request; the server-side model orchestrator chooses tools."""

    model_config = ConfigDict(extra="forbid")
    message: str = Field(..., min_length=1, max_length=4000)
    ui_tool_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        description="Optional controlled UI shortcut. This is distinct from model-selected tool calls.",
    )
    ui_tool_arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments for ui_tool_name only; ignored unless the controlled shortcut is supplied.",
    )


class AssistantConfirmToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation_id: str = Field(..., min_length=1, max_length=64)
    tool_name: str = Field(..., min_length=1, max_length=80)
    parameter_summary: str = Field(..., min_length=2, max_length=12000)


class AssistantErrorDetail(BaseModel):
    code: str
    message: str
    stage: str
    session_id: str | None = None
    tool_name: str | None = None


class AssistantErrorResponse(BaseModel):
    detail: AssistantErrorDetail
