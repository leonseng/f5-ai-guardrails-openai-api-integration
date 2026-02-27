import json
import logging
import os
from typing import Optional
from urllib.parse import urlparse, parse_qs

from fastapi import FastAPI, Request, Response, Header
from fastapi.middleware.cors import CORSMiddleware
import httpx
from dotenv import load_dotenv

from guardrails import GuardrailsClient
from helper import (
    filter_response_headers,
    merge_query_params,
    inject_system_prompt,
    scan_prompt_with_guardrail,
    handle_streaming_request,
    handle_non_streaming_request
)

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

# Add CORS middleware to allow browser requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    req_body_json = await inject_system_prompt(CONFIG, req_body_json)

    # Scan prompt if enabled
    error_response, req_body_json = await scan_prompt_with_guardrail(CONFIG, guardrails_client, req_body_json, resp_streaming, enable_guardrail, enable_redact)
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
        return await handle_streaming_request(CONFIG, guardrails_client, req_body_json, headers, dict(request.query_params), original_model, enable_guardrail, enable_redact)
    else:
        logger.debug("Handling non-streaming chat completion request")
        return await handle_non_streaming_request(CONFIG, guardrails_client, req_body_json, headers, dict(request.query_params), original_model, enable_guardrail, enable_redact)


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
    merged_params = merge_query_params(CONFIG, dict(request.query_params))
    logger.debug(f"Merged query params: {merged_params}")

    async with httpx.AsyncClient(timeout=CONFIG["TIMEOUT"]) as client:
        resp = await client.get(
            f"{CONFIG['OPENAI_API_URL'].rstrip('/')}/models",
            headers=headers,
            params=merged_params
        )

    # Filter out headers that should not be forwarded
    response_headers = filter_response_headers(dict(resp.headers))

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=response_headers
    )
