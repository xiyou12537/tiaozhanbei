from __future__ import annotations

import json

import pika

from backend.core.config import settings


def publish_message(queue_name: str, payload: dict) -> None:
    params = pika.URLParameters(settings.RABBITMQ_URL)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)
    channel.basic_publish(
        exchange="",
        routing_key=queue_name,
        body=json.dumps(payload).encode("utf-8"),
    )
    connection.close()


def consume_messages(queue_name: str, handler, limit: int | None = None) -> int:
    params = pika.URLParameters(settings.RABBITMQ_URL)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)
    processed = 0

    while True:
        method_frame, _header_frame, body = channel.basic_get(queue=queue_name, auto_ack=False)
        if method_frame is None:
            break
        payload = json.loads(body.decode("utf-8"))
        handler(payload)
        channel.basic_ack(delivery_tag=method_frame.delivery_tag)
        processed += 1
        if limit is not None and processed >= limit:
            break

    connection.close()
    return processed
