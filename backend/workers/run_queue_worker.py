from __future__ import annotations

import time

from backend.orchestrator.dispatcher import RabbitMQStageDispatcher
from backend.db.repositories.workflow_repository import WorkflowRepository
from backend.workers.consumer import consume_stage_queue


def main() -> None:
    repository = WorkflowRepository()
    dispatcher = RabbitMQStageDispatcher()
    while True:
        consume_stage_queue(repository=repository, dispatcher=dispatcher, limit=1)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
