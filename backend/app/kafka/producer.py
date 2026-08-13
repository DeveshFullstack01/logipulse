"""Thin wrapper around aiokafka's producer.

Kept separate from the simulator so the API can publish events too
(the Chaos Panel on Day 6 will use this).
"""
import logging

from aiokafka import AIOKafkaProducer

from app.core.config import settings
from app.schemas.events import ShipmentEvent

log = logging.getLogger(__name__)


class EventProducer:
    def __init__(self, topic: str | None = None):
        self.topic = topic or settings.kafka_topic
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap,
            # 'all' = wait for the broker to confirm the write before we
            # consider it sent. Slower, but we don't silently lose events.
            acks="all",
            enable_idempotence=True,
            linger_ms=50,
        )
        await self._producer.start()
        log.info("Producer connected to %s (topic=%s)", settings.kafka_bootstrap, self.topic)

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
            log.info("Producer stopped")

    async def publish(self, event: ShipmentEvent) -> None:
        if not self._producer:
            raise RuntimeError("Producer not started — call start() first")
        await self._producer.send_and_wait(
            self.topic,
            key=event.key,
            value=event.to_json(),
        )

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *exc):
        await self.stop()
