"""Tests for query parameter support (Azure AI Foundry compatibility)"""
import os
import pytest
from fastapi.testclient import TestClient
import respx
from httpx import Response

from tests.mocks.openai_mock import (
    create_chat_completion_response,
    create_models_response
)


class TestQueryParameterParsing:
    """Test URL parsing and query parameter extraction"""
    
    def test_url_with_query_params(self):
        """Test parsing URL with query parameters"""
        os.environ["OPENAI_API_URL"] = "http://test.azure.com/models?api-version=2024-05-01-preview"
        os.environ["PROXY_TIMEOUT"] = "30"
        
        import importlib
        import main
        importlib.reload(main)
        
        assert main.CONFIG["OPENAI_API_URL"] == "http://test.azure.com/models"
        assert "api-version" in main.CONFIG["OPENAI_API_QUERY_PARAMS"]
        assert main.CONFIG["OPENAI_API_QUERY_PARAMS"]["api-version"] == ["2024-05-01-preview"]
    
    def test_url_without_query_params(self):
        """Test parsing URL without query parameters (backwards compatibility)"""
        os.environ["OPENAI_API_URL"] = "http://localhost:11434/v1"
        os.environ["PROXY_TIMEOUT"] = "30"
        
        import importlib
        import main
        importlib.reload(main)
        
        assert main.CONFIG["OPENAI_API_URL"] == "http://localhost:11434/v1"
        assert main.CONFIG["OPENAI_API_QUERY_PARAMS"] == {}
    
    def test_url_with_multiple_query_params(self):
        """Test parsing URL with multiple query parameters"""
        os.environ["OPENAI_API_URL"] = "http://test.azure.com/models?api-version=2024-05&format=json"
        os.environ["PROXY_TIMEOUT"] = "30"
        
        import importlib
        import main
        importlib.reload(main)
        
        assert main.CONFIG["OPENAI_API_URL"] == "http://test.azure.com/models"
        assert "api-version" in main.CONFIG["OPENAI_API_QUERY_PARAMS"]
        assert "format" in main.CONFIG["OPENAI_API_QUERY_PARAMS"]


class TestQueryParameterMerging:
    """Test query parameter merging logic"""
    
    @pytest.fixture
    def client_with_url_params(self):
        """Create client with URL containing query parameters"""
        os.environ["OPENAI_API_URL"] = "http://mock-backend:11434/v1?api-version=2024-05-01-preview"
        os.environ["PROXY_TIMEOUT"] = "30"
        os.environ["F5_AI_GUARDRAILS_API_URL"] = "http://mock-guardrails/api"
        os.environ["F5_AI_GUARDRAILS_API_TOKEN"] = "mock-token"
        os.environ["F5_AI_GUARDRAILS_PROJECT_ID"] = "mock-project"
        os.environ["F5_AI_GUARDRAILS_SCAN_PROMPT"] = ""
        os.environ["F5_AI_GUARDRAILS_SCAN_RESPONSE"] = ""
        
        import importlib
        import main
        importlib.reload(main)
        
        return TestClient(main.app)
    
    def test_merge_no_client_params(self, client_with_url_params):
        """Test merging when client provides no query parameters"""
        with respx.mock(base_url="http://mock-backend:11434") as mock_backend:
            mock_backend.post("/v1/chat/completions").mock(
                return_value=Response(
                    status_code=200,
                    json=create_chat_completion_response("test response")
                )
            )
            
            response = client_with_url_params.post(
                "/v1/chat/completions",
                json={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": "test"}]
                }
            )
            
            assert response.status_code == 200
            # Verify the mock was called with the URL query param
            assert mock_backend.calls.last.request.url.params.get("api-version") == "2024-05-01-preview"
    
    def test_merge_with_client_params(self, client_with_url_params):
        """Test merging when client provides additional query parameters"""
        with respx.mock(base_url="http://mock-backend:11434") as mock_backend:
            mock_backend.post("/v1/chat/completions").mock(
                return_value=Response(
                    status_code=200,
                    json=create_chat_completion_response("test response")
                )
            )
            
            response = client_with_url_params.post(
                "/v1/chat/completions?client-param=value",
                json={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": "test"}]
                }
            )
            
            assert response.status_code == 200
            # Verify both params are present
            request_params = mock_backend.calls.last.request.url.params
            assert request_params.get("api-version") == "2024-05-01-preview"
            assert request_params.get("client-param") == "value"
    
    def test_url_params_override_client_params(self, client_with_url_params):
        """Test that URL parameters take precedence over client parameters"""
        with respx.mock(base_url="http://mock-backend:11434") as mock_backend:
            mock_backend.post("/v1/chat/completions").mock(
                return_value=Response(
                    status_code=200,
                    json=create_chat_completion_response("test response")
                )
            )
            
            # Client tries to set api-version, but URL param should override
            response = client_with_url_params.post(
                "/v1/chat/completions?api-version=old-version",
                json={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": "test"}]
                }
            )
            
            assert response.status_code == 200
            # URL param should override client param
            assert mock_backend.calls.last.request.url.params.get("api-version") == "2024-05-01-preview"


class TestEndpointsWithQueryParams:
    """Test endpoints with query parameters"""
    
    @pytest.fixture
    def client_with_url_params(self):
        """Create client with URL containing query parameters"""
        os.environ["OPENAI_API_URL"] = "http://mock-backend:11434/v1?api-version=2024-05-01-preview"
        os.environ["PROXY_TIMEOUT"] = "30"
        os.environ["F5_AI_GUARDRAILS_API_URL"] = "http://mock-guardrails/api"
        os.environ["F5_AI_GUARDRAILS_API_TOKEN"] = "mock-token"
        os.environ["F5_AI_GUARDRAILS_PROJECT_ID"] = "mock-project"
        os.environ["F5_AI_GUARDRAILS_SCAN_PROMPT"] = ""
        os.environ["F5_AI_GUARDRAILS_SCAN_RESPONSE"] = ""
        
        import importlib
        import main
        importlib.reload(main)
        
        return TestClient(main.app)
    
    def test_chat_completions_non_streaming_with_url_params(self, client_with_url_params):
        """Test non-streaming chat completions with URL query parameters"""
        with respx.mock(base_url="http://mock-backend:11434") as mock_backend:
            mock_backend.post("/v1/chat/completions").mock(
                return_value=Response(
                    status_code=200,
                    json=create_chat_completion_response("Hello!")
                )
            )
            
            response = client_with_url_params.post(
                "/v1/chat/completions",
                json={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": False
                }
            )
            
            assert response.status_code == 200
            assert mock_backend.calls.last.request.url.params.get("api-version") == "2024-05-01-preview"
    
    def test_chat_completions_streaming_with_url_params(self, client_with_url_params):
        """Test streaming chat completions with URL query parameters"""
        with respx.mock(base_url="http://mock-backend:11434") as mock_backend:
            from tests.mocks.openai_mock import create_streaming_response
            
            mock_backend.post("/v1/chat/completions").mock(
                return_value=Response(
                    status_code=200,
                    content=create_streaming_response("Hello!"),
                    headers={"content-type": "text/event-stream"}
                )
            )
            
            response = client_with_url_params.post(
                "/v1/chat/completions",
                json={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": True
                }
            )
            
            assert response.status_code == 200
            assert mock_backend.calls.last.request.url.params.get("api-version") == "2024-05-01-preview"
    
    def test_models_endpoint_with_url_params(self, client_with_url_params):
        """Test models endpoint with URL query parameters"""
        with respx.mock(base_url="http://mock-backend:11434") as mock_backend:
            mock_backend.get("/v1/models").mock(
                return_value=Response(
                    status_code=200,
                    json=create_models_response(["gpt-4"])
                )
            )
            
            response = client_with_url_params.get("/v1/models")
            
            assert response.status_code == 200
            assert mock_backend.calls.last.request.url.params.get("api-version") == "2024-05-01-preview"
