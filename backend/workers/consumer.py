from backend.core.config import settings
from backend.db.repositories.workflow_repository import WorkflowRepository
from backend.infrastructure.messaging.rabbitmq import consume_messages
from backend.orchestrator.dispatcher import RabbitMQStageDispatcher
from backend.orchestrator.engine import OrchestratorEngine
from backend.workers.runtime import HANDLERS, run_stage


def process_stage_message(message: dict, repository: WorkflowRepository | None = None, dispatcher=None) -> dict:
    repository = repository or WorkflowRepository()
    dispatcher = dispatcher or RabbitMQStageDispatcher()
    engine = OrchestratorEngine(dispatcher=dispatcher, repository=repository)
    return engine.process_stage_message(message)


def consume_stage_queue(
    queue_name: str = settings.WORKFLOW_STAGE_QUEUE,
    *,
    repository: WorkflowRepository | None = None,
    dispatcher=None,
    limit: int | None = None,
) -> int:
    repository = repository or WorkflowRepository()
    dispatcher = dispatcher or RabbitMQStageDispatcher(queue_name=queue_name)
    return consume_messages(
        queue_name,
        lambda payload: process_stage_message(payload, repository=repository, dispatcher=dispatcher),
        limit=limit,
    )
