from __future__ import annotations

import hmac
import json
import re
from collections.abc import Callable

from fastapi import FastAPI, Request, Response

from gateway.store import EventStore
from gateway.verify import verify as _verify

MAX_BODY = 1 * 1024 * 1024  # 1 MiB (BHV-8, F-3)

_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def create_app(
    secrets: dict[str, bytes],
    store: EventStore,
    now: Callable[[], int],
    read_token: str,
) -> FastAPI:
    app = FastAPI()

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.post("/webhooks/{source}")
    async def receive_webhook(source: str, request: Request) -> Response:
        # F-3 (BHV-8): reject on Content-Length before reading body
        content_length_hdr = request.headers.get("Content-Length")
        if content_length_hdr is not None:
            try:
                if int(content_length_hdr) > MAX_BODY:
                    return Response(status_code=413)
            except ValueError:
                pass

        # Resolve secret — unknown source → 401, same as bad sig (INV-6: no oracle)
        secret = secrets.get(source)
        if secret is None:
            return Response(status_code=401)

        # Read raw body BEFORE any JSON parsing (ADR-2); bound to MAX_BODY (F-3)
        raw = await request.body()
        if len(raw) > MAX_BODY:
            return Response(status_code=413)

        # Validate required headers
        x_timestamp = request.headers.get("X-Timestamp")
        x_signature = request.headers.get("X-Signature")
        if x_timestamp is None or x_signature is None:
            return Response(status_code=401)

        try:
            timestamp = int(x_timestamp)
        except ValueError:
            return Response(status_code=401)

        # F-2 (BHV-2): validate hex ASCII before calling verify (TypeError guard)
        if not x_signature.startswith("sha256="):
            return Response(status_code=401)
        hex_part = x_signature[7:]
        if not _HEX_RE.match(hex_part):
            return Response(status_code=401)

        # Verify signature + freshness — no write before this (INV-1, INV-2, INV-3)
        if not _verify(secret, timestamp, raw, x_signature, now()):
            return Response(status_code=401)  # INV-6: no oracle, same 401

        # Parse JSON (BHV-7)
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return Response(status_code=400)

        if not isinstance(payload, dict):
            return Response(status_code=400)

        if not all(k in payload for k in ("event_id", "type", "data")):
            return Response(status_code=400)

        event_id = payload["event_id"]

        # Idempotent store (INV-4, BHV-1, BHV-4)
        if store.add_if_absent(event_id, payload):
            return Response(
                content=json.dumps({"status": "accepted", "event_id": event_id}),
                status_code=202,
                media_type="application/json",
            )
        return Response(
            content=json.dumps({"status": "duplicate", "event_id": event_id}),
            status_code=409,
            media_type="application/json",
        )

    @app.get("/events/{event_id}")
    async def get_event(event_id: str, request: Request) -> Response:
        # F-1 (INV-7): constant-time token check — absent or invalid → 401, no payload
        token = request.headers.get("X-Read-Token", "")
        if not hmac.compare_digest(token.encode(), read_token.encode()):
            return Response(status_code=401)
        payload = store.get(event_id)
        if payload is None:
            return Response(status_code=404)
        return Response(
            content=json.dumps(payload),
            status_code=200,
            media_type="application/json",
        )

    return app
