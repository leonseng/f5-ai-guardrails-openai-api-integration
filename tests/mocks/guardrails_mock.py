from typing import Dict, Any, Optional
import uuid
from datetime import datetime


def create_guardrails_scan_response(
    outcome: str,
    input_text: str,
    redacted_text: Optional[str] = None,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Create a mock F5 AI Guardrails scan response matching the real API schema.
    
    Args:
        outcome: One of "cleared", "flagged", "redacted"
        input_text: The original input text
        redacted_text: The redacted text (only used if outcome is "redacted")
        verbose: Whether to include verbose details (currently unused, for future)
    
    Returns:
        Response matching the actual F5 AI Guardrails API schema
    """
    response = {
        "id": str(uuid.uuid4()),
        "result": {
            "scannerResults": [
                {
                    "scannerId": str(uuid.uuid4()),
                    "scannerVersionMeta": {
                        "id": str(uuid.uuid4()),
                        "createdAt": datetime.utcnow().isoformat() + "+00:00",
                        "createdBy": "system",
                        "name": "2025-04",
                        "published": True,
                        "description": ""
                    },
                    "outcome": "passed" if outcome != "flagged" else "failed",
                    "data": {
                        "type": "custom"
                    },
                    "customConfig": False,
                    "startedDate": datetime.utcnow().isoformat() + "+00:00",
                    "completedDate": datetime.utcnow().isoformat() + "+00:00",
                    "scanDirection": "request"
                }
            ],
            "outcome": outcome
        }
    }
    
    # Add redactedInput field when outcome is "redacted"
    if outcome == "redacted":
        response["redactedInput"] = redacted_text if redacted_text else input_text
    
    return response


def create_cleared_response(input_text: str, verbose: bool = False) -> Dict[str, Any]:
    """Create a 'cleared' scan response (no issues found)"""
    return create_guardrails_scan_response("cleared", input_text, verbose=verbose)


def create_flagged_response(input_text: str, verbose: bool = False) -> Dict[str, Any]:
    """Create a 'flagged' scan response (content blocked)"""
    return create_guardrails_scan_response("flagged", input_text, verbose=verbose)


def create_redacted_response(
    input_text: str,
    redacted_text: str,
    verbose: bool = False
) -> Dict[str, Any]:
    """Create a 'redacted' scan response (content redacted)"""
    return create_guardrails_scan_response("redacted", input_text, redacted_text, verbose)


def create_error_response(
    message: str,
    status_code: int = 500
) -> Dict[str, Any]:
    """Create an error response from guardrails API"""
    return {
        "error": {
            "message": message,
            "code": status_code
        }
    }
