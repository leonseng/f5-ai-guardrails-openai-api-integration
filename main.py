import json
import logging
import os
import time

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
import httpx
from dotenv import load_dotenv

import helper

load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:11434")
TIMEOUT = float(os.getenv("PROXY_TIMEOUT", "30"))
F5_AI_GUARDRAILS_API_URL = str(os.getenv("F5_AI_GUARDRAILS_API_URL"))
F5_AI_GUARDRAILS_API_TOKEN = str(os.getenv("F5_AI_GUARDRAILS_API_TOKEN"))
F5_AI_GUARDRAILS_PROJECT_ID = str(os.getenv("F5_AI_GUARDRAILS_PROJECT_ID"))
F5_AI_GUARDRAILS_SCAN_PROMPT = bool(os.getenv("F5_AI_GUARDRAILS_SCAN_PROMPT"))
F5_AI_GUARDRAILS_SCAN_RESPONSE = bool(os.getenv("F5_AI_GUARDRAILS_SCAN_RESPONSE"))
F5_AI_GUARDRAILS_REDACT_PROMPT = bool(os.getenv("F5_AI_GUARDRAILS_REDACT_PROMPT"))
F5_AI_GUARDRAILS_REDACT_RESPONSE = bool(os.getenv("F5_AI_GUARDRAILS_REDACT_RESPONSE"))

app = FastAPI(title="OpenAI Proxy")
logger = logging.getLogger('uvicorn.error')

if F5_AI_GUARDRAILS_SCAN_PROMPT or F5_AI_GUARDRAILS_SCAN_RESPONSE:
    GuardrailClient = helper.GuardrailClient(
        api_url=F5_AI_GUARDRAILS_API_URL,
        api_token=F5_AI_GUARDRAILS_API_TOKEN,
        project_id=F5_AI_GUARDRAILS_PROJECT_ID
    )

logger.info(f"Proxy to backend: {BACKEND_URL}")


@app.api_route("/v1/chat/completions", methods=["POST"])
async def chat_completion(request: Request):
    """Proxy prompts to backend"""

    req_body_text = await request.body()
    try:
        req_body_json = json.loads(req_body_text)
    except json.JSONDecodeError:
        return Response(content="Invalid JSON body: {raw_req_body}", status_code=400)

    resp_streaming = req_body_json.get("stream", False)

    if F5_AI_GUARDRAILS_SCAN_PROMPT:
        try:
            latest_msg = req_body_json["messages"][-1]
            if latest_msg.get("role") != "user":
                if resp_streaming:
                    return StreamingResponse(
                        helper.stream_error_response("Last message must have role 'user'"),
                        status_code=400,
                        media_type="text/event-stream"
                    )
                else:
                    return Response(content="Last message must have role 'user'", status_code=400)
            scan_results = await GuardrailClient.scan(latest_msg["content"])

            if scan_results.outcome == "flagged":
                if resp_streaming:
                    return StreamingResponse(
                        helper.stream_error_response("Prompt blocked by Guardrail"),
                        status_code=400,
                        media_type="text/event-stream"
                    )
                else:
                    return Response(content="Prompt blocked by Guardrail", status_code=400)

            if scan_results.outcome == "redacted" and F5_AI_GUARDRAILS_REDACT_PROMPT:
                req_body_json["messages"][-1]["content"] = scan_results.output
        # fail open
        except httpx.ConnectError as e:
            logger.error(f"Guardrail connection error: {e}")
        except Exception as e:
            logger.error(f"Guardrail scan error: {e}")

    # proxy request to BACKEND_URL
    # rewrite host header to BACKEND_URL host. note that header can be in upper or lower case
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    headers["host"] = BACKEND_URL.replace("http://", "").replace("https://", "").split("/")[0]

    req_body_text = json.dumps(req_body_json)

    if resp_streaming:
        # buffer streaming response from backend for scanning, then stream scanned response to client
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Make streaming request to backend
            async with client.stream(
                "POST",
                f"{BACKEND_URL.rstrip('/')}/v1/chat/completions",
                headers=headers,
                params=dict(request.query_params),
                content=req_body_text,
            ) as resp:
                # Buffer the complete streaming response
                resp_status_code = resp.status_code
                logger.debug(f"Response status: {resp_status_code}")

                resp_headers = resp.headers
                logger.debug(f"Response headers: {resp_headers}")

                if resp_status_code != 200:
                    await resp.aread()
                    logger.debug(f"Response body: {resp.content}")
                    return StreamingResponse(
                        helper.stream_error_response("Bad response from backend"),
                        status_code=400,
                        media_type="text/event-stream"
                    )

                resp_msg, metadata = await helper.buffer_streaming_response(resp)
                logger.debug(f"Response message: {resp_msg}")

        if F5_AI_GUARDRAILS_SCAN_RESPONSE:
            # validate guardrail results
            try:
                scan_results = await GuardrailClient.scan(resp_msg)

                if scan_results.outcome == "flagged":
                    return StreamingResponse(
                        helper.stream_error_response("Response blocked by Guardrail"),
                        status_code=400,
                        media_type="text/event-stream"
                    )

                if scan_results.outcome == "redacted" and F5_AI_GUARDRAILS_REDACT_RESPONSE:
                    resp_msg = scan_results.output

            # fail open
            except httpx.ConnectError as e:
                logger.error(f"Guardrail connection error: {e}")
            except Exception as e:
                # fail open
                logger.error(f"Guardrail scan error: {e}")

        return StreamingResponse(
            helper.stream_processed_response(
                resp_msg,
                metadata.get("model", req_body_json.get("model", "unknown")),
                metadata.get("id", f"chatcmpl-{int(time.time())}")
            ),
            status_code=resp_status_code,
            media_type="text/event-stream",
            headers=resp_headers
        )
    else:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{BACKEND_URL.rstrip('/')}/v1/chat/completions",
                headers=headers,
                params=dict(request.query_params),
                content=req_body_text
            )

        resp_status_code = resp.status_code
        logger.debug(f"Response status: {resp_status_code}")
        resp_headers = resp.headers
        logger.debug(f"Response headers: {resp_headers}")
        resp_body_text = resp.content
        logger.debug(f"Response body: {resp_body_text}")

        if F5_AI_GUARDRAILS_SCAN_RESPONSE and resp.status_code == 200:
            try:
                resp_body_json = json.loads(resp_body_text)
                resp_msg = resp_body_json["choices"][0]["message"]["content"]
                scan_results = await GuardrailClient.scan(resp_msg)

                if scan_results.outcome == "flagged":
                    return Response(content="Response blocked by Guardrail", status_code=400)

                if scan_results.outcome == "redacted" and F5_AI_GUARDRAILS_REDACT_RESPONSE:
                    resp_body_json["choices"][0]["message"]["content"] = scan_results.output
                    resp_body_text = json.dumps(resp_body_json)
                    # replace content-length in headers (regardless of header is in upper or lower case)
                    resp_headers = {k: v for k, v in resp_headers.items() if k.lower() != "content-length"}
                    resp_headers["content-length"] = str(len(resp_body_text))

            except json.JSONDecodeError:
                return Response(content=f"Invalid JSON body: {resp_body_text}", status_code=400)
            # fail open
            except ValueError:
                logger.warning(f"Not valid OpenAI API response: {resp_body_text}")
            except httpx.ConnectError as e:
                logger.error(f"Guardrail connection error: {e}")
            except Exception as e:
                logger.error(f"Guardrail scan error: {e}")

        return Response(
            content=resp_body_text,
            status_code=resp_status_code,
            headers=resp_headers
        )


@app.api_route("/v1/models", methods=["GET"])
async def models(request: Request):
    """List models"""
    # proxy request to BACKEND_URL

    # rewrite host header to BACKEND_URL host. note that header can be in upper or lower case
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    headers["host"] = BACKEND_URL.replace("http://", "").replace("https://", "").split("/")[0]

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            f"{BACKEND_URL.rstrip('/')}/v1/models",
            headers=headers,
            params=dict(request.query_params)
        )

    resp_status_code = resp.status_code
    resp_headers = resp.headers
    resp_body_text = resp.content

    return Response(
        content=resp_body_text,
        status_code=resp_status_code,
        headers=resp_headers
    )
