import json
import logging
import os
import time
from typing import AsyncGenerator, Dict, Any, Optional
from urllib.parse import urlparse, parse_qs

from fastapi import FastAPI, Request, Response, Header
from fastapi.responses import StreamingResponse
import httpx
from dotenv import load_dotenv

from guardrails import GuardrailsClient

load_dotenv(override=False)

YES_VALUES = ("true", 1, "yes", "1")

# Parse OPENAI_API_URL to extract base URL and query parameters
openai_api_url_raw = os.getenv("OPENAI_API_URL", "http://127.0.0.1:11434")
parsed_url = urlparse(openai_api_url_raw)
openai_api_base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
openai_api_query_params = parse_qs(parsed_url.query)

CONFIG = {
    "DEBUG": os.getenv("DEBUG", "false").lower() in YES_VALUES,
    "OPENAI_API_URL": openai_api_base_url,
    "OPENAI_API_QUERY_PARAMS": openai_api_query_params,
    "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
    "MODEL": os.getenv("MODEL"),
    "TIMEOUT": float(os.getenv("PROXY_TIMEOUT", "30")),
    "SYSTEM_PROMPT": os.getenv("SYSTEM_PROMPT"),
    "F5_AI_GUARDRAILS_API_URL": os.getenv("F5_AI_GUARDRAILS_API_URL"),
    "F5_AI_GUARDRAILS_API_TOKEN": os.getenv("F5_AI_GUARDRAILS_API_TOKEN"),
    "F5_AI_GUARDRAILS_PROJECT_ID": os.getenv("F5_AI_GUARDRAILS_PROJECT_ID"),
    "F5_AI_GUARDRAILS_SCAN_PROMPT": os.getenv("F5_AI_GUARDRAILS_SCAN_PROMPT") in YES_VALUES,
    "F5_AI_GUARDRAILS_SCAN_RESPONSE": os.getenv("F5_AI_GUARDRAILS_SCAN_RESPONSE") in YES_VALUES,
    "F5_AI_GUARDRAILS_REDACT_PROMPT": os.getenv("F5_AI_GUARDRAILS_REDACT_PROMPT") in YES_VALUES,
    "F5_AI_GUARDRAILS_REDACT_RESPONSE": os.getenv("F5_AI_GUARDRAILS_REDACT_RESPONSE") in YES_VALUES,
}

app = FastAPI(title="OpenAI Proxy")
logger = logging.getLogger('uvicorn.error')

# Set log level based on DEBUG config
logger.setLevel(logging.DEBUG if CONFIG["DEBUG"] else logging.INFO)

# Log all configuration entries at initialization
for key, value in CONFIG.items():
    # Mask sensitive values
    if "TOKEN" in key or "KEY" in key:
        display_value = "***" if value else None
    else:
        display_value = value
    logger.debug(f"{key}: {display_value}")

# Initialize guardrails client if credentials are configured
guardrails_client = None
if CONFIG["F5_AI_GUARDRAILS_API_URL"] and CONFIG["F5_AI_GUARDRAILS_API_TOKEN"] and CONFIG["F5_AI_GUARDRAILS_PROJECT_ID"]:
    guardrails_client = GuardrailsClient(
        api_url=CONFIG["F5_AI_GUARDRAILS_API_URL"],
        api_token=CONFIG["F5_AI_GUARDRAILS_API_TOKEN"],
        project_id=CONFIG["F5_AI_GUARDRAILS_PROJECT_ID"]
    )
    logger.info("F5 AI Guardrails client initialized")
else:
    logger.info("F5 AI Guardrails not configured")

logger.info(f"Proxy to backend: {CONFIG['OPENAI_API_URL']}")


def merge_query_params(client_params: dict) -> dict:
    """
    Merge client query parameters with URL query parameters.
    URL parameters take precedence over client parameters.
    """
    merged = dict(client_params)
    
    # Add URL params, converting lists to single values
    for key, value in CONFIG["OPENAI_API_QUERY_PARAMS"].items():
        # parse_qs returns lists, take first value
        merged[key] = value[0] if isinstance(value, list) and len(value) > 0 else value
    
    return merged


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


async def inject_system_prompt(req_body_json: dict) -> dict:
    """
    Inject system prompt if configured and not already present.
    """
    if CONFIG["SYSTEM_PROMPT"] and "messages" in req_body_json:
        messages = req_body_json["messages"]
        has_system = any(msg.get("role") == "system" for msg in messages)
        if not has_system:
            req_body_json["messages"] = [{"role": "system", "content": CONFIG["SYSTEM_PROMPT"]}] + messages
            logger.debug("Injected system prompt")
    return req_body_json


async def scan_prompt_with_guardrail(req_body_json: dict, streaming: bool, enable_guardrail: Optional[bool] = None, enable_redact: Optional[bool] = None) -> tuple[StreamingResponse | Response | None, dict]:
    """
    Scan prompt and return error response if flagged, or modified request if redacted.
    Returns (error_response, modified_request) tuple.
    """
    # Check header override or fall back to environment variable
    scan_enabled = enable_guardrail if enable_guardrail is not None else CONFIG["F5_AI_GUARDRAILS_SCAN_PROMPT"]
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
        redact_enabled = enable_redact if enable_redact is not None else CONFIG["F5_AI_GUARDRAILS_REDACT_PROMPT"]
        if scan_results.outcome == "redacted" and redact_enabled:
            req_body_json["messages"][-1]["content"] = scan_results.output

    except httpx.ConnectError as e:
        logger.error(f"Guardrail connection error: {e}")
    except Exception as e:
        logger.error(f"Guardrail scan error: {e}")

    return None, req_body_json


async def scan_response_with_guardrail(response_text: str, streaming: bool, enable_guardrail: Optional[bool] = None, enable_redact: Optional[bool] = None) -> tuple[StreamingResponse | Response | None, str]:
    """
    Scan response and return error or modified text.
    Returns (error_response, modified_text) tuple.
    """
    # Check header override or fall back to environment variable
    scan_enabled = enable_guardrail if enable_guardrail is not None else CONFIG["F5_AI_GUARDRAILS_SCAN_RESPONSE"]
    if not scan_enabled or not guardrails_client:
        return None, response_text

    try:
        scan_results = await guardrails_client.scan(response_text)

        if scan_results.outcome == "flagged":
            return create_error_response("Response blocked by Guardrail", streaming), ""

        # Check header override or fall back to environment variable for redaction
        redact_enabled = enable_redact if enable_redact is not None else CONFIG["F5_AI_GUARDRAILS_REDACT_RESPONSE"]
        if scan_results.outcome == "redacted" and redact_enabled:
            return None, scan_results.output

    except httpx.ConnectError as e:
        logger.error(f"Guardrail connection error: {e}")
    except Exception as e:
        logger.error(f"Guardrail scan error: {e}")

    return None, response_text


async def handle_streaming_request(req_body_json: dict, headers: dict, query_params: dict, original_model: str | None = None, enable_guardrail: Optional[bool] = None, enable_redact: Optional[bool] = None):
    """Handle streaming chat completion request"""

    logger.debug(f"Request headers: {headers}")
    logger.debug(f"Request body: {req_body_json}")

    # Merge client query params with URL query params
    merged_params = merge_query_params(query_params)
    logger.debug(f"Merged query params: {merged_params}")

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{CONFIG['OPENAI_API_URL'].rstrip('/')}/chat/completions",
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
                                if "content" in delta:
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

    # Scan response if enabled
    error_response, modified_msg = await scan_response_with_guardrail(resp_msg, streaming=True, enable_guardrail=enable_guardrail, enable_redact=enable_redact)
    if error_response:
        return error_response

    # Use original model from client if provided, otherwise use backend's model
    response_model = original_model or metadata.get("model", req_body_json.get("model", "unknown"))

    # Filter out headers that should not be forwarded
    response_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in ("content-length", "content-encoding", "transfer-encoding")
    }

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


async def handle_non_streaming_request(req_body_json: dict, headers: dict, query_params: dict, original_model: str | None = None, enable_guardrail: Optional[bool] = None, enable_redact: Optional[bool] = None):
    """Handle non-streaming chat completion request"""

    logger.debug(f"Request headers: {headers}")
    logger.debug(f"Request body: {req_body_json}")

    # Merge client query params with URL query params
    merged_params = merge_query_params(query_params)
    logger.debug(f"Merged query params: {merged_params}")

    async with httpx.AsyncClient(timeout=CONFIG["TIMEOUT"]) as client:
        resp = await client.post(
            f"{CONFIG['OPENAI_API_URL'].rstrip('/')}/chat/completions",
            headers=headers,
            params=merged_params,
            content=json.dumps(req_body_json).encode('utf-8')
        )

    resp_status_code = resp.status_code
    logger.debug(f"Response status: {resp_status_code}")
    resp_headers = resp.headers
    logger.debug(f"Response headers: {resp_headers}")
    resp_body_text = resp.content
    logger.debug(f"Response body: {resp_body_text}")

    # Scan response if enabled and successful
    scan_enabled = (
        enable_guardrail if enable_guardrail is not None else CONFIG["F5_AI_GUARDRAILS_SCAN_RESPONSE"]) and guardrails_client
    if scan_enabled and resp_status_code == 200:
        try:
            resp_body_json = json.loads(resp_body_text)
            resp_msg = resp_body_json["choices"][0]["message"]["content"]

            error_response, modified_msg = await scan_response_with_guardrail(resp_msg, streaming=False, enable_guardrail=enable_guardrail, enable_redact=enable_redact)
            if error_response:
                return error_response

            if modified_msg != resp_msg:
                resp_body_json["choices"][0]["message"]["content"] = modified_msg
                resp_body_text = json.dumps(resp_body_json)

                # recalculate content-length if present in response
                if "content-length" in resp_headers:
                    resp_headers = {k: v for k, v in resp_headers.items() if k.lower() != "content-length"}
                    resp_headers["content-length"] = str(len(resp_body_text))

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

                # recalculate content-length if present in response
                if "content-length" in resp_headers:
                    resp_headers = {k: v for k, v in resp_headers.items() if k.lower() != "content-length"}
                    resp_headers["content-length"] = str(len(resp_body_text))

        except json.JSONDecodeError:
            logger.warning(f"Could not restore original model - invalid JSON: {resp_body_text}")
        except Exception as e:
            logger.error(f"Error restoring original model: {e}")

    return Response(
        content=resp_body_text,
        status_code=resp_status_code,
        headers=resp_headers
    )


@app.api_route("/v1/chat/completions", methods=["POST"])
async def chat_completion(
    request: Request,
    x_enable_guardrail: Optional[str] = Header(alias="x-enable-guardrail", default=None),
    x_redact: Optional[str] = Header(alias="x-redact", default=None)
):
    """Proxy prompts to backend with optional guardrail scanning"""

    # Parse header flags - if not provided, use None to let backend settings take precedence
    enable_guardrail = str(x_enable_guardrail).lower() == "true" if x_enable_guardrail is not None else None
    enable_redact = str(x_redact).lower() == "true" if x_redact is not None else None

    # Parse request body
    req_body_text = await request.body()
    try:
        req_body_json = json.loads(req_body_text)
    except json.JSONDecodeError:
        return Response(content="Invalid JSON body", status_code=400)

    resp_streaming = req_body_json.get("stream", False)

    # Inject system prompt if configured
    req_body_json = await inject_system_prompt(req_body_json)

    # Scan prompt if enabled
    error_response, req_body_json = await scan_prompt_with_guardrail(req_body_json, resp_streaming, enable_guardrail, enable_redact)
    if error_response:
        return error_response

    # Store original model from client request
    original_model = req_body_json.get("model")

    # Override model if MODEL env var is set
    if CONFIG["MODEL"]:
        req_body_json["model"] = CONFIG["MODEL"]
        logger.debug(f"Overriding model from '{original_model}' to '{CONFIG['MODEL']}'")

    # Prepare headers for backend request (exclude content-length as httpx will set it)
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    headers["host"] = CONFIG["OPENAI_API_URL"].replace("http://", "").replace("https://", "").split("/")[0]

    # Override Authorization header if OPENAI_API_KEY env var is set
    if CONFIG["OPENAI_API_KEY"]:
        headers["Authorization"] = f"Bearer {CONFIG['OPENAI_API_KEY']}"
        logger.debug("Overriding Authorization header with OPENAI_API_KEY")

    # Route to appropriate handler
    if resp_streaming:
        logger.debug("Handling streaming chat completion request")
        return await handle_streaming_request(req_body_json, headers, dict(request.query_params), original_model, enable_guardrail, enable_redact)
    else:
        logger.debug("Handling non-streaming chat completion request")
        return await handle_non_streaming_request(req_body_json, headers, dict(request.query_params), original_model, enable_guardrail, enable_redact)


@app.api_route("/v1/models", methods=["GET"])
async def models(request: Request):
    """List models"""
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    headers["host"] = CONFIG["OPENAI_API_URL"].replace("http://", "").replace("https://", "").split("/")[0]

    # Override Authorization header if OPENAI_API_KEY env var is set
    if CONFIG["OPENAI_API_KEY"]:
        headers["Authorization"] = f"Bearer {CONFIG['OPENAI_API_KEY']}"
        logger.debug("Overriding Authorization header with OPENAI_API_KEY")

    # Merge client query params with URL query params
    merged_params = merge_query_params(dict(request.query_params))
    logger.debug(f"Merged query params: {merged_params}")

    async with httpx.AsyncClient(timeout=CONFIG["TIMEOUT"]) as client:
        resp = await client.get(
            f"{CONFIG['OPENAI_API_URL'].rstrip('/')}/models",
            headers=headers,
            params=merged_params
        )

    # Filter out headers that should not be forwarded
    response_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in ("content-length", "content-encoding", "transfer-encoding")
    }

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=response_headers
    )
