from collections import namedtuple
import json
import logging
import time
from typing import AsyncGenerator, Dict, Any, Optional

import httpx

logger = logging.getLogger("uvicorn.error")

GuardrailScanResult = namedtuple("PGuardrailScanResultoint", "outcome output")


class GuardrailClient():
    def __init__(self, api_url: str, api_token: str, project_id: str, timeout: float = 30.0):
        self.api_url = api_url
        self.api_token = api_token
        self.project_id = project_id
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    async def scan(
        self,
        input_text: str,
        force_enabled: Optional[list] = [],
        external_metadata: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
        timeout: float = 30.0,
    ) -> GuardrailScanResult:
        payload = {
            "externalMetadata": external_metadata,
            "forceEnabled": force_enabled,
            "input": input_text,
            "project": self.project_id,
            "verbose": verbose,
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{self.api_url.rstrip('/')}/scans", headers=self.headers, json=payload)

        output = input_text
        try:
            resp.raise_for_status()
            scan_resp_body = resp.json()
            scan_outcome = scan_resp_body["result"]["outcome"]
            logger.debug(f"Guardrail scan results: {scan_outcome}.")

            if scan_outcome not in ["cleared", "flagged", "redacted"]:
                raise ValueError(
                    f"Unknown Guardrail scan outcome: {scan_outcome}")

            if scan_outcome == "redacted":
                output = scan_resp_body["redactedInput"]

        except json.JSONDecodeError as e:
            # fail open
            logger.error("Guardrail scan response is not valid JSON")
            raise e
        except httpx.HTTPStatusError as e:
            # fail open
            logger.error(f"Guardrail scan failed: {e}")
            raise e

        return GuardrailScanResult(scan_resp_body["result"]["outcome"], output)


async def buffer_streaming_response(response: httpx.Response) -> tuple[str, Dict[str, Any]]:
    """
    Buffer the complete streaming response from the backend.
    Returns the complete text and metadata.
    """
    complete_text = ""
    metadata = {
        "id": None,
        "model": None,
        "created": None,
        "finish_reason": None
    }

    async for line in response.aiter_lines():
        if not line.strip() or line.strip() == "data: [DONE]":
            continue

        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])  # Remove "data: " prefix

                # Extract metadata from first chunk
                if metadata["id"] is None:
                    metadata["id"] = data.get("id")
                    metadata["model"] = data.get("model")
                    metadata["created"] = data.get("created")

                # Accumulate content
                if "choices" in data and len(data["choices"]) > 0:
                    delta = data["choices"][0].get("delta", {})
                    if "content" in delta:
                        complete_text += delta["content"]

                    # Capture finish reason
                    finish_reason = data["choices"][0].get("finish_reason")
                    if finish_reason:
                        metadata["finish_reason"] = finish_reason

            except json.JSONDecodeError:
                continue

    return complete_text, metadata


async def stream_processed_response(
    response_text: str,
    model: str,
    request_id: str,
    chunk_size: int = 5
) -> AsyncGenerator[str, None]:
    """
    Stream the processed response back to the client in OpenAI format.
    """
    # Send initial chunk with role
    chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": ""},
                "finish_reason": None
            }
        ]
    }
    yield f"data: {json.dumps(chunk)}\n\n"

    # Stream the content in chunks
    for i in range(0, len(response_text), chunk_size):
        text_chunk = response_text[i:i + chunk_size]

        chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": text_chunk},
                    "finish_reason": None
                }
            ]
        }
        yield f"data: {json.dumps(chunk)}\n\n"

    # Send final chunk with finish_reason
    final_chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": ""},
                "finish_reason": "stop",
                "stop_reason": None
            }
        ]
    }
    yield f"data: {json.dumps(final_chunk)}\n\n"
    yield "data: [DONE]\n\n"


async def stream_error_response(msg: str) -> AsyncGenerator[str, None]:
    error_data = {
        "error": {
            "message": msg,
            "type": "content_policy_violation",
            "code": "content_blocked"
        }
    }
    # Send the error as a data event
    yield f"data: {json.dumps(error_data)}\n\n"
