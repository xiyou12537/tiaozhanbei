from __future__ import annotations

from backend.core.config import settings
from backend.infrastructure.messaging.rabbitmq import publish_message

DEFAULT_STAGE_QUEUE = settings.WORKFLOW_STAGE_QUEUE


def build_stage_message(workflow_id: str, stage_name: str, attempt_no: int, trace_id: str) -> dict:
    return {
        "workflow_id": workflow_id,
        "stage_name": stage_name,
        "attempt_no": attempt_no,
        "trace_id": trace_id,
    }


class RabbitMQStageDispatcher:
    def __init__(self, queue_name: str = DEFAULT_STAGE_QUEUE):
        self.queue_name = queue_name

    def dispatch(self, payload: dict) -> None:
        publish_message(self.queue_name, payload)
