import os
from typing import Dict, Callable, Optional, List, Generator, Any
import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

from tests.mocks.openai_mock import (
    create_chat_completion_response,
    create_streaming_response,
    create_models_response
)


@pytest.fixture
def test_env_vars() -> Generator[Dict[str, str], None, None]:
    """Set up test environment variables"""
    original_env = os.environ.copy()
    
    # Set default test environment variables
    test_vars = {
        "BACKEND_URL": "http://mock-backend:11434",
        "PROXY_TIMEOUT": "30",
        "SYSTEM_PROMPT": "",
        "F5_AI_GUARDRAILS_API_URL": "http://mock-guardrails/api",
        "F5_AI_GUARDRAILS_API_TOKEN": "mock-token",
        "F5_AI_GUARDRAILS_PROJECT_ID": "mock-project",
        # Note: bool(os.getenv("X")) returns True for any non-empty string including "false"
        # So we use empty strings to represent False
        "F5_AI_GUARDRAILS_SCAN_PROMPT": "",
        "F5_AI_GUARDRAILS_SCAN_RESPONSE": "",
        "F5_AI_GUARDRAILS_REDACT_PROMPT": "",
        "F5_AI_GUARDRAILS_REDACT_RESPONSE": "",
    }
    
    for key, value in test_vars.items():
        os.environ[key] = value
    
    yield test_vars
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def client(test_env_vars: Dict[str, str]) -> TestClient:
    """Create a FastAPI test client"""
    # Import here to ensure environment variables are set
    import main
    return TestClient(main.app)


@pytest.fixture
def mock_backend() -> Generator[respx.MockRouter, None, None]:
    """Create a respx mock for the backend API"""
    with respx.mock(base_url="http://mock-backend:11434", assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def mock_guardrails() -> Generator[respx.MockRouter, None, None]:
    """Create a respx mock for the F5 AI Guardrails API"""
    with respx.mock(base_url="http://mock-guardrails", assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def setup_mock_chat_completion(mock_backend: respx.MockRouter) -> Callable[[str, bool, int], None]:
    """Helper fixture to setup mock chat completion responses"""
    def _setup(response_text: str = "Hello! How can I help you?", streaming: bool = False, status_code: int = 200) -> None:
        if streaming:
            content = create_streaming_response(response_text)
            mock_backend.post("/v1/chat/completions").mock(
                return_value=Response(
                    status_code=status_code,
                    content=content,
                    headers={"content-type": "text/event-stream"}
                )
            )
        else:
            content = create_chat_completion_response(response_text)
            mock_backend.post("/v1/chat/completions").mock(
                return_value=Response(
                    status_code=status_code,
                    json=content
                )
            )
    return _setup


@pytest.fixture
def setup_mock_models(mock_backend: respx.MockRouter) -> Callable[[Optional[List[str]]], None]:
    """Helper fixture to setup mock models endpoint"""
    def _setup(models: Optional[List[str]] = None) -> None:
        content = create_models_response(models)
        mock_backend.get("/v1/models").mock(
            return_value=Response(
                status_code=200,
                json=content
            )
        )
    return _setup


@pytest.fixture
def setup_mock_guardrails_scan(mock_guardrails: respx.MockRouter) -> Callable[[str, str, Optional[str]], None]:
    """Helper fixture to setup mock guardrails scan responses"""
    def _setup(outcome: str = "cleared", input_text: str = "test", redacted_text: Optional[str] = None) -> None:
        from tests.mocks.guardrails_mock import (
            create_cleared_response,
            create_flagged_response,
            create_redacted_response
        )
        
        if outcome == "cleared":
            response = create_cleared_response(input_text)
        elif outcome == "flagged":
            response = create_flagged_response(input_text)
        elif outcome == "redacted":
            response = create_redacted_response(input_text, redacted_text or "[REDACTED]")
        else:
            raise ValueError(f"Unknown outcome: {outcome}")
        
        mock_guardrails.post("/api/scans").mock(
            return_value=Response(
                status_code=200,
                json=response
            )
        )
    return _setup

