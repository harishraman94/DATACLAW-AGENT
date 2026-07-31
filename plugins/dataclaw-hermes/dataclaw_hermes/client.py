"""HTTP/SSE client for the pinned Hermes Runs API."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from dataclaw_hermes.config import HermesConfig


class HermesAPIError(RuntimeError):
    pass


class HermesClient:
    def __init__(
        self,
        config: HermesConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        headers = {"Accept": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        self._client = httpx.AsyncClient(
            base_url=config.url,
            headers=headers,
            timeout=httpx.Timeout(config.request_timeout_seconds),
            transport=transport,
        )
        self._closed = False

    async def health(self) -> dict[str, Any]:
        response = await self._client.get("/health")
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "ok":
            raise HermesAPIError("Hermes liveness probe did not return ok")
        return payload

    async def capabilities(self) -> dict[str, Any]:
        response = await self._client.get("/v1/capabilities")
        response.raise_for_status()
        return response.json()

    async def models(self) -> dict[str, Any]:
        response = await self._client.get("/v1/models")
        response.raise_for_status()
        return response.json()

    async def toolsets(self) -> dict[str, Any]:
        response = await self._client.get("/v1/toolsets")
        response.raise_for_status()
        return response.json()

    async def create_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post("/v1/runs", json=payload)
        if response.status_code != 202:
            raise HermesAPIError(
                f"Hermes run creation failed ({response.status_code}): "
                f"{response.text[:500]}"
            )
        data = response.json()
        if not isinstance(data.get("run_id"), str) or not data["run_id"]:
            raise HermesAPIError("Hermes did not return a run_id")
        return data

    async def stream_run_events(
        self, runtime_run_id: str
    ) -> AsyncIterator[dict[str, Any]]:
        async with self._client.stream(
            "GET",
            f"/v1/runs/{runtime_run_id}/events",
            timeout=None,
        ) as response:
            response.raise_for_status()
            data_lines: list[str] = []
            async for line in response.aiter_lines():
                if not line:
                    if not data_lines:
                        continue
                    raw = "\n".join(data_lines)
                    data_lines.clear()
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise HermesAPIError(
                            "Invalid JSON in Hermes event stream"
                        ) from exc
                    if isinstance(payload, dict):
                        yield payload
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
            if data_lines:
                payload = json.loads("\n".join(data_lines))
                if isinstance(payload, dict):
                    yield payload

    async def status(self, runtime_run_id: str) -> dict[str, Any]:
        response = await self._client.get(
            f"/v1/runs/{runtime_run_id}",
            timeout=self.config.reconnect_timeout_seconds,
        )
        if response.status_code == 404:
            return {"status": "unknown", "run_id": runtime_run_id}
        response.raise_for_status()
        return response.json()

    async def cancel(self, runtime_run_id: str) -> dict[str, Any]:
        response = await self._client.post(
            f"/v1/runs/{runtime_run_id}/stop",
            timeout=self.config.reconnect_timeout_seconds,
        )
        if response.status_code == 404:
            return {"status": "unknown", "run_id": runtime_run_id}
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._client.aclose()
