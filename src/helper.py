import json
import logging
import time
from typing import AsyncGenerator, Dict, Any, Optional

from fastapi.responses import StreamingResponse
from fastapi import Response
import httpx

logger = logging.getLogger('uvicorn.error')


# =============================================================================
# HTTP/Response Utilities
# =============================================================================

def filter_response_headers(headers: dict) -> dict:
    """
    Filter out headers that should not be forwarded to the client.
    """
    return {
        k: v for k, v in headers.items()
        if k.lower() not in ("content-length", "content-encoding", "transfer-encoding", "server", "date")
    }


def merge_query_params(config: dict, client_params: dict) -> dict:
    """
    Merge client query parameters with URL query parameters.
    URL parameters take precedence over client parameters.
    """
    merged = dict(client_params)

    # Add URL params, converting lists to single values
    for key, value in config["OPENAI_API_QUERY_PARAMS"].items():
        # parse_qs returns lists, take first value
        merged[key] = value[0] if isinstance(value, list) and len(value) > 0 else value

    return merged


def create_error_response(message: str, streaming: bool):
    """Create error response in appropriate format"""
    if streaming:
        return StreamingResponse(
            stream_error_response_to_client(message),
            status_code=400,
            media_type="text/event-stream"
        )
    else:
        return Response(content=message, status_code=400)


# =============================================================================
# Streaming Utilities
# =============================================================================

async def stream_processed_response_to_client(
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


async def stream_error_response_to_client(msg: str) -> AsyncGenerator[str, None]:
    error_data = {
        "error": {
            "message": msg,
            "type": "content_policy_violation",
            "code": "content_blocked"
        }
    }
    # Send the error as a data event
    yield f"data: {json.dumps(error_data)}\n\n"


# =============================================================================
# Request Processing
# =============================================================================

async def inject_system_prompt(config: dict, req_body_json: dict) -> dict:
    """
    Inject system prompt if configured and not already present.
    """
    if config["SYSTEM_PROMPT"] and "messages" in req_body_json:
        messages = req_body_json["messages"]
        has_system = any(msg.get("role") == "system" for msg in messages)
        if not has_system:
            req_body_json["messages"] = [{"role": "system", "content": config["SYSTEM_PROMPT"]}] + messages
            logger.debug("Injected system prompt")
    return req_body_json


async def scan_prompt_with_guardrail(config: dict, guardrails_client, req_body_json: dict, streaming: bool, enable_guardrail: Optional[bool] = None, enable_redact: Optional[bool] = None) -> tuple[StreamingResponse | Response | None, dict]:
    """
    Scan prompt and return error response if flagged, or modified request if redacted.
    Returns (error_response, modified_request) tuple.
    """
    # Check header override or fall back to environment variable
    scan_enabled = enable_guardrail if enable_guardrail is not None else config["F5_AI_GUARDRAILS_SCAN_PROMPT"]
    if not scan_enabled or not guardrails_client:
        return None, req_body_json

    try:
        latest_msg = req_body_json["messages"][-1]
        if latest_msg.get("role") != "user":
            return create_error_response("Last message must have role 'user'", streaming), {}

        scan_results = await guardrails_client.scan(latest_msg["content"])

        if scan_results.outcome == "flagged":
            return create_error_response("Prompt blocked by Guardrail", streaming), {}

        # Check header override or fall back to environment variable for redaction
        redact_enabled = enable_redact if enable_redact is not None else config["F5_AI_GUARDRAILS_REDACT_PROMPT"]
        if scan_results.outcome == "redacted" and redact_enabled:
            req_body_json["messages"][-1]["content"] = scan_results.output

    except httpx.ConnectError as e:
        logger.error(f"Guardrail connection error: {e}")
    except Exception as e:
        logger.error(f"Guardrail scan error: {e}")

    return None, req_body_json


async def scan_response_with_guardrail(config: dict, guardrails_client, response_text: str, streaming: bool, enable_guardrail: Optional[bool] = None, enable_redact: Optional[bool] = None) -> tuple[StreamingResponse | Response | None, str]:
    """
    Scan response and return error or modified text.
    Returns (error_response, modified_text) tuple.
    """
    # Check header override or fall back to environment variable
    scan_enabled = enable_guardrail if enable_guardrail is not None else config["F5_AI_GUARDRAILS_SCAN_RESPONSE"]
    if not scan_enabled or not guardrails_client:
        return None, response_text

    try:
        scan_results = await guardrails_client.scan(response_text)

        if scan_results.outcome == "flagged":
            return create_error_response("Response blocked by Guardrail", streaming), ""

        # Check header override or fall back to environment variable for redaction
        redact_enabled = enable_redact if enable_redact is not None else config["F5_AI_GUARDRAILS_REDACT_RESPONSE"]
        if scan_results.outcome == "redacted" and redact_enabled:
            return None, scan_results.output

    except httpx.ConnectError as e:
        logger.error(f"Guardrail connection error: {e}")
    except Exception as e:
        logger.error(f"Guardrail scan error: {e}")

    return None, response_text


# =============================================================================
# Request Handlers
# =============================================================================

async def handle_streaming_request(config: dict, guardrails_client, req_body_json: dict, headers: dict, query_params: dict, original_model: str | None = None, enable_guardrail: Optional[bool] = None, enable_redact: Optional[bool] = None):
    """Handle streaming chat completion request"""

    logger.debug(f"Request headers: {headers}")
    logger.debug(f"Request body: {req_body_json}")

    # Merge client query params with URL query params
    merged_params = merge_query_params(config, query_params)
    logger.debug(f"Merged query params: {merged_params}")

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{config['OPENAI_API_URL'].rstrip('/')}/chat/completions",
            headers=headers,
            params=merged_params,
            content=json.dumps(req_body_json).encode('utf-8'),
        ) as resp:
            resp_status_code = resp.status_code
            logger.debug(f"Response status: {resp_status_code}")
            logger.debug(f"Response headers: {resp.headers}")

            if resp_status_code != 200:
                await resp.aread()
                logger.debug(f"Response body: {resp.content}")
                return StreamingResponse(
                    stream_error_response_to_client("Bad response from backend"),
                    status_code=400,
                    media_type="text/event-stream"
                )

            async def buffer_streaming_response_from_backend(response: httpx.Response) -> tuple[str, Dict[str, Any]]:
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
                                if "content" in delta and delta["content"] is not None:
                                    complete_text += delta["content"]

                                # Capture finish reason
                                finish_reason = data["choices"][0].get("finish_reason")
                                if finish_reason:
                                    metadata["finish_reason"] = finish_reason

                        except json.JSONDecodeError:
                            continue

                return complete_text, metadata

            resp_msg, metadata = await buffer_streaming_response_from_backend(resp)
            logger.debug(f"Response message: {resp_msg}")
            logger.debug(f"Response headers: {resp.headers}")

    # Scan response if enabled
    error_response, modified_msg = await scan_response_with_guardrail(config, guardrails_client, resp_msg, streaming=True, enable_guardrail=enable_guardrail, enable_redact=enable_redact)
    if error_response:
        return error_response

    # Use original model from client if provided, otherwise use backend's model
    response_model = original_model or metadata.get("model", req_body_json.get("model", "unknown"))

    # Filter out headers that should not be forwarded
    response_headers = filter_response_headers(dict(resp.headers))

    return StreamingResponse(
        stream_processed_response_to_client(
            modified_msg,
            response_model,
            metadata.get("id", f"chatcmpl-{int(time.time())}")
        ),
        status_code=200,
        media_type="text/event-stream",
        headers=response_headers
    )


async def handle_non_streaming_request(config: dict, guardrails_client, req_body_json: dict, headers: dict, query_params: dict, original_model: str | None = None, enable_guardrail: Optional[bool] = None, enable_redact: Optional[bool] = None):
    """Handle non-streaming chat completion request"""

    logger.debug(f"Request headers: {headers}")
    logger.debug(f"Request body: {req_body_json}")

    # Merge client query params with URL query params
    merged_params = merge_query_params(config, query_params)
    logger.debug(f"Merged query params: {merged_params}")

    async with httpx.AsyncClient(timeout=config["TIMEOUT"]) as client:
        resp = await client.post(
            f"{config['OPENAI_API_URL'].rstrip('/')}/chat/completions",
            headers=headers,
            params=merged_params,
            content=json.dumps(req_body_json).encode('utf-8')
        )

    resp_status_code = resp.status_code
    logger.debug(f"Response status: {resp_status_code}")
    logger.debug(f"Response headers: {resp.headers}")

    # Read response body (httpx auto-decompresses gzip)
    resp_body_text = resp.text
    logger.debug(f"Response body: {resp_body_text}")

    # Scan response if enabled and successful
    scan_enabled = (
        enable_guardrail if enable_guardrail is not None else config["F5_AI_GUARDRAILS_SCAN_RESPONSE"]) and guardrails_client
    if scan_enabled and resp_status_code == 200:
        try:
            resp_body_json = json.loads(resp_body_text)
            resp_msg = resp_body_json["choices"][0]["message"]["content"]

            error_response, modified_msg = await scan_response_with_guardrail(config, guardrails_client, resp_msg, streaming=False, enable_guardrail=enable_guardrail, enable_redact=enable_redact)
            if error_response:
                return error_response

            if modified_msg != resp_msg:
                resp_body_json["choices"][0]["message"]["content"] = modified_msg
                resp_body_text = json.dumps(resp_body_json)

        except json.JSONDecodeError:
            return Response(content=f"Invalid JSON body: {resp_body_text}", status_code=400)
        except ValueError:
            logger.warning(f"Not valid OpenAI API response: {resp_body_text}")
        except httpx.ConnectError as e:
            logger.error(f"Guardrail connection error: {e}")
        except Exception as e:
            logger.error(f"Guardrail scan error: {e}")

    # Restore original model in response if it was overridden
    if original_model and resp_status_code == 200:
        try:
            resp_body_json = json.loads(resp_body_text)
            if "model" in resp_body_json:
                resp_body_json["model"] = original_model
                resp_body_text = json.dumps(resp_body_json)

        except json.JSONDecodeError:
            logger.warning(f"Could not restore original model - invalid JSON: {resp_body_text}")
        except Exception as e:
            logger.error(f"Error restoring original model: {e}")

    # Filter out headers that shouldn't be forwarded
    filtered_headers = filter_response_headers(dict(resp.headers))

    return Response(
        content=resp_body_text,
        status_code=resp_status_code,
        headers=filtered_headers
    )
