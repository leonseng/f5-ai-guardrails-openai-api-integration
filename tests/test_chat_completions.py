import json


class TestChatCompletionsBasic:
    """Test basic chat completion functionality"""
    
    def test_non_streaming_chat_completion_mock(
        self, client, mock_backend, setup_mock_chat_completion
    ):
        """Test non-streaming chat completion with mock backend"""
        setup_mock_chat_completion(response_text="Hello! How can I help you?")
        
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["choices"][0]["message"]["content"] == "Hello! How can I help you?"
    
    def test_streaming_chat_completion_mock(
        self, client, mock_backend, setup_mock_chat_completion
    ):
        """Test streaming chat completion with mock backend"""
        setup_mock_chat_completion(
            response_text="Hello! How can I help you?",
            streaming=True
        )
        
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True
            }
        )
        
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        
        # Verify streaming response contains expected content
        content = response.text
        assert "data: " in content
        assert "Hello" in content
        assert "[DONE]" in content


class TestSystemPromptInjection:
    """Test system prompt injection functionality"""
    
    def test_system_prompt_injection(
        self, client, mock_backend, setup_mock_chat_completion, test_env_vars
    ):
        """Test that system prompt is injected when configured"""
        import os
        import importlib
        import main
        from fastapi.testclient import TestClient
        
        os.environ["SYSTEM_PROMPT"] = "You are a helpful assistant."
        importlib.reload(main)
        
        client = TestClient(main.app)
        setup_mock_chat_completion()
        
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False
            }
        )
        
        assert response.status_code == 200
        
        # Verify the backend received the system prompt
        last_request = mock_backend.calls.last.request
        body = json.loads(last_request.content)
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][0]["content"] == "You are a helpful assistant."
    
    def test_system_prompt_not_duplicated(
        self, client, mock_backend, setup_mock_chat_completion, test_env_vars
    ):
        """Test that system prompt is not duplicated if already present"""
        import os
        import importlib
        import main
        from fastapi.testclient import TestClient
        
        os.environ["SYSTEM_PROMPT"] = "You are a helpful assistant."
        importlib.reload(main)
        
        client = TestClient(main.app)
        setup_mock_chat_completion()
        
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "You are a test assistant."},
                    {"role": "user", "content": "Hello"}
                ],
                "stream": False
            }
        )
        
        assert response.status_code == 200
        
        # Verify the backend only has one system message
        last_request = mock_backend.calls.last.request
        body = json.loads(last_request.content)
        system_messages = [m for m in body["messages"] if m["role"] == "system"]
        assert len(system_messages) == 1
        assert system_messages[0]["content"] == "You are a test assistant."


class TestErrorHandling:
    """Test error handling"""
    
    def test_invalid_json_body(self, client):
        """Test handling of invalid JSON in request body"""
        response = client.post(
            "/v1/chat/completions",
            content="invalid json",
            headers={"content-type": "application/json"}
        )
        
        assert response.status_code == 400
        assert "Invalid JSON body" in response.text
    
    def test_backend_error_non_streaming(
        self, client, mock_backend, test_env_vars
    ):
        """Test handling of backend errors in non-streaming mode"""
        from httpx import Response
        
        mock_backend.post("/v1/chat/completions").mock(
            return_value=Response(status_code=500, content=b"Internal Server Error")
        )
        
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False
            }
        )
        
        assert response.status_code == 500
    
    def test_backend_error_streaming(
        self, client, mock_backend, test_env_vars
    ):
        """Test handling of backend errors in streaming mode"""
        from httpx import Response
        
        mock_backend.post("/v1/chat/completions").mock(
            return_value=Response(status_code=500, content=b"Internal Server Error")
        )
        
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True
            }
        )
        
        assert response.status_code == 400
        assert "text/event-stream" in response.headers.get("content-type", "")
