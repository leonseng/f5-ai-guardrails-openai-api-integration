import json
import time
from typing import List, Dict, Any, Optional


def create_chat_completion_response(
    message_content: str,
    model: str = "gpt-4o-mini",
    request_id: Optional[str] = None,
    streaming: bool = False
) -> Dict[str, Any]:
    """Create a non-streaming chat completion response"""
    if request_id is None:
        request_id = f"chatcmpl-{int(time.time())}"
    
    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": message_content
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30
        }
    }


def create_streaming_chunk(
    content: str = "",
    model: str = "gpt-4o-mini",
    request_id: Optional[str] = None,
    finish_reason: Optional[str] = None,
    role: Optional[str] = None
) -> str:
    """Create a single streaming response chunk in SSE format"""
    if request_id is None:
        request_id = f"chatcmpl-{int(time.time())}"
    
    delta = {}
    if role:
        delta["role"] = role
    if content:
        delta["content"] = content
    
    chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason
            }
        ]
    }
    
    return f"data: {json.dumps(chunk)}\n\n"


def create_streaming_response(
    message_content: str,
    model: str = "gpt-4o-mini",
    request_id: Optional[str] = None,
    chunk_size: int = 5
) -> str:
    """Create a complete streaming chat completion response"""
    if request_id is None:
        request_id = f"chatcmpl-{int(time.time())}"
    
    chunks = []
    
    # Initial chunk with role
    chunks.append(create_streaming_chunk("", model, request_id, role="assistant"))
    
    # Content chunks
    for i in range(0, len(message_content), chunk_size):
        text_chunk = message_content[i:i + chunk_size]
        chunks.append(create_streaming_chunk(text_chunk, model, request_id))
    
    # Final chunk with finish_reason
    chunks.append(create_streaming_chunk("", model, request_id, finish_reason="stop"))
    
    # Done marker
    chunks.append("data: [DONE]\n\n")
    
    return "".join(chunks)


def create_models_response(models: Optional[List[str]] = None) -> Dict[str, Any]:
    """Create a models list response"""
    if models is None:
        models = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
    
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "openai"
            }
            for model_id in models
        ]
    }


def create_error_response(
    message: str,
    error_type: str = "invalid_request_error",
    code: Optional[str] = None
) -> Dict[str, Any]:
    """Create an error response"""
    error = {
        "message": message,
        "type": error_type
    }
    if code:
        error["code"] = code
    
    return {"error": error}


def create_streaming_error_response(message: str) -> str:
    """Create a streaming error response in SSE format"""
    error_data = {
        "error": {
            "message": message,
            "type": "content_policy_violation",
            "code": "content_blocked"
        }
    }
    return f"data: {json.dumps(error_data)}\n\n"
