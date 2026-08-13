"""Tracks live browser connections and fans messages out to them."""
import asyncio
import logging

from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        log.info("WebSocket connected (%d total)", len(self._connections))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)
        log.info("WebSocket disconnected (%d remain)", len(self._connections))

    @property
    def count(self) -> int:
        return len(self._connections)

    async def broadcast(self, message: str) -> None:
        """Send to everyone, dropping any connection that has gone away.

        A browser tab closing mid-send raises here; if we didn't collect and
        remove those, dead sockets would accumulate for the life of the
        process and every broadcast would get slower.
        """
        if not self._connections:
            return

        async with self._lock:
            targets = list(self._connections)

        dead = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)
            log.info("Dropped %d dead connection(s)", len(dead))


manager = ConnectionManager()
