import json
import os


class TestPromptScanning:
    """Test prompt scanning functionality"""
    
    def test_prompt_cleared(
        self, client, mock_backend, mock_guardrails, 
        setup_mock_chat_completion, setup_mock_guardrails_scan,
        test_env_vars
    ):
        """Test prompt scanning with 'cleared' outcome"""
        import importlib
        import main
        
        os.environ["F5_AI_GUARDRAILS_SCAN_PROMPT"] = "true"
        importlib.reload(main)
        
        client_new = client.__class__(main.app)
        
        setup_mock_chat_completion()
        setup_mock_guardrails_scan(outcome="cleared", input_text="Hello")
        
        response = client_new.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data
    
    def test_prompt_flagged_non_streaming(
        self, client, mock_backend, mock_guardrails,
        setup_mock_guardrails_scan, test_env_vars
    ):
        """Test prompt scanning with 'flagged' outcome in non-streaming mode"""
        import importlib
        import main
        
        os.environ["F5_AI_GUARDRAILS_SCAN_PROMPT"] = "true"
        importlib.reload(main)
        
        client_new = client.__class__(main.app)
        
        setup_mock_guardrails_scan(outcome="flagged", input_text="Bad content")
        
        response = client_new.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Bad content"}],
                "stream": False
            }
        )
        
        assert response.status_code == 400
        assert "Prompt blocked by Guardrail" in response.text
    
    def test_prompt_flagged_streaming(
        self, client, mock_backend, mock_guardrails,
        setup_mock_guardrails_scan, test_env_vars
    ):
        """Test prompt scanning with 'flagged' outcome in streaming mode"""
        import importlib
        import main
        
        os.environ["F5_AI_GUARDRAILS_SCAN_PROMPT"] = "true"
        importlib.reload(main)
        
        client_new = client.__class__(main.app)
        
        setup_mock_guardrails_scan(outcome="flagged", input_text="Bad content")
        
        response = client_new.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Bad content"}],
                "stream": True
            }
        )
        
        assert response.status_code == 400
        assert "text/event-stream" in response.headers.get("content-type", "")
    
    def test_prompt_redacted_with_redaction_enabled(
        self, client, mock_backend, mock_guardrails,
        setup_mock_chat_completion, setup_mock_guardrails_scan,
        test_env_vars
    ):
        """Test prompt redaction when redaction is enabled"""
        import importlib
        import main
        
        os.environ["F5_AI_GUARDRAILS_SCAN_PROMPT"] = "true"
        os.environ["F5_AI_GUARDRAILS_REDACT_PROMPT"] = "true"
        importlib.reload(main)
        
        client_new = client.__class__(main.app)
        
        setup_mock_chat_completion()
        setup_mock_guardrails_scan(
            outcome="redacted",
            input_text="Contains PII: 123-45-6789",
            redacted_text="Contains PII: [REDACTED]"
        )
        
        response = client_new.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Contains PII: 123-45-6789"}],
                "stream": False
            }
        )
        
        assert response.status_code == 200
        
        # Verify the backend received the redacted content
        last_request = mock_backend.calls.last.request
        body = json.loads(last_request.content)
        assert body["messages"][-1]["content"] == "Contains PII: [REDACTED]"
    
    def test_prompt_redacted_with_redaction_disabled(
        self, client, mock_backend, mock_guardrails,
        setup_mock_chat_completion, setup_mock_guardrails_scan,
        test_env_vars
    ):
        """Test prompt redaction when redaction is disabled"""
        import importlib
        import main
        
        os.environ["F5_AI_GUARDRAILS_SCAN_PROMPT"] = "true"
        os.environ["F5_AI_GUARDRAILS_REDACT_PROMPT"] = ""  # Empty string = False
        importlib.reload(main)
        
        client_new = client.__class__(main.app)
        
        setup_mock_chat_completion()
        setup_mock_guardrails_scan(
            outcome="redacted",
            input_text="Contains PII: 123-45-6789",
            redacted_text="Contains PII: [REDACTED]"
        )
        
        response = client_new.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Contains PII: 123-45-6789"}],
                "stream": False
            }
        )
        
        assert response.status_code == 200
        
        # Verify the backend received the original content
        last_request = mock_backend.calls.last.request
        body = json.loads(last_request.content)
        assert body["messages"][-1]["content"] == "Contains PII: 123-45-6789"


class TestResponseScanning:
    """Test response scanning functionality"""
    
    def test_response_cleared_non_streaming(
        self, client, mock_backend, mock_guardrails,
        setup_mock_chat_completion, setup_mock_guardrails_scan,
        test_env_vars
    ):
        """Test response scanning with 'cleared' outcome in non-streaming mode"""
        import importlib
        import main
        
        os.environ["F5_AI_GUARDRAILS_SCAN_RESPONSE"] = "true"
        importlib.reload(main)
        
        client_new = client.__class__(main.app)
        
        setup_mock_chat_completion(response_text="Hello! How can I help you?")
        setup_mock_guardrails_scan(outcome="cleared", input_text="Hello! How can I help you?")
        
        response = client_new.post(
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
    
    def test_response_cleared_streaming(
        self, client, mock_backend, mock_guardrails,
        setup_mock_chat_completion, setup_mock_guardrails_scan,
        test_env_vars
    ):
        """Test response scanning with 'cleared' outcome in streaming mode"""
        import importlib
        import main
        
        os.environ["F5_AI_GUARDRAILS_SCAN_RESPONSE"] = "true"
        importlib.reload(main)
        
        client_new = client.__class__(main.app)
        
        setup_mock_chat_completion(response_text="Hello! How can I help you?", streaming=True)
        setup_mock_guardrails_scan(outcome="cleared", input_text="Hello! How can I help you?")
        
        response = client_new.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True
            }
        )
        
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
    
    def test_response_flagged_non_streaming(
        self, client, mock_backend, mock_guardrails,
        setup_mock_chat_completion, setup_mock_guardrails_scan,
        test_env_vars
    ):
        """Test response scanning with 'flagged' outcome in non-streaming mode"""
        import importlib
        import main
        
        os.environ["F5_AI_GUARDRAILS_SCAN_PROMPT"] = ""  # Disabled
        os.environ["F5_AI_GUARDRAILS_SCAN_RESPONSE"] = "true"
        importlib.reload(main)
        
        client_new = client.__class__(main.app)
        
        setup_mock_chat_completion(response_text="Inappropriate content")
        setup_mock_guardrails_scan(outcome="flagged", input_text="Inappropriate content")
        
        response = client_new.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False
            }
        )
        
        assert response.status_code == 400
        assert "Response blocked by Guardrail" in response.text
    
    def test_response_flagged_streaming(
        self, client, mock_backend, mock_guardrails,
        setup_mock_chat_completion, setup_mock_guardrails_scan,
        test_env_vars
    ):
        """Test response scanning with 'flagged' outcome in streaming mode"""
        import importlib
        import main
        
        os.environ["F5_AI_GUARDRAILS_SCAN_RESPONSE"] = "true"
        importlib.reload(main)
        
        client_new = client.__class__(main.app)
        
        setup_mock_chat_completion(response_text="Inappropriate content", streaming=True)
        setup_mock_guardrails_scan(outcome="flagged", input_text="Inappropriate content")
        
        response = client_new.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True
            }
        )
        
        assert response.status_code == 400
        assert "text/event-stream" in response.headers.get("content-type", "")
    
    def test_response_redacted_with_redaction_enabled(
        self, client, mock_backend, mock_guardrails,
        setup_mock_chat_completion, setup_mock_guardrails_scan,
        test_env_vars
    ):
        """Test response redaction when redaction is enabled"""
        import importlib
        import main
        
        os.environ["F5_AI_GUARDRAILS_SCAN_RESPONSE"] = "true"
        os.environ["F5_AI_GUARDRAILS_REDACT_RESPONSE"] = "true"
        importlib.reload(main)
        
        client_new = client.__class__(main.app)
        
        setup_mock_chat_completion(response_text="Here is PII: 123-45-6789")
        setup_mock_guardrails_scan(
            outcome="redacted",
            input_text="Here is PII: 123-45-6789",
            redacted_text="Here is PII: [REDACTED]"
        )
        
        response = client_new.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["choices"][0]["message"]["content"] == "Here is PII: [REDACTED]"
    
    def test_response_redacted_with_redaction_disabled(
        self, client, mock_backend, mock_guardrails,
        setup_mock_chat_completion, setup_mock_guardrails_scan,
        test_env_vars
    ):
        """Test response redaction when redaction is disabled"""
        import importlib
        import main
        
        os.environ["F5_AI_GUARDRAILS_SCAN_RESPONSE"] = "true"
        os.environ["F5_AI_GUARDRAILS_REDACT_RESPONSE"] = ""  # Empty string = False
        importlib.reload(main)
        
        client_new = client.__class__(main.app)
        
        setup_mock_chat_completion(response_text="Here is PII: 123-45-6789")
        setup_mock_guardrails_scan(
            outcome="redacted",
            input_text="Here is PII: 123-45-6789",
            redacted_text="Here is PII: [REDACTED]"
        )
        
        response = client_new.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["choices"][0]["message"]["content"] == "Here is PII: 123-45-6789"


class TestGuardrailsDisabled:
    """Test scenarios when guardrails are disabled"""
    
    def test_no_scanning_when_prompt_scan_disabled(
        self, client, mock_backend, mock_guardrails,
        setup_mock_chat_completion, test_env_vars
    ):
        """Test that no scanning occurs when prompt scanning is disabled"""
        import importlib
        import main
        
        os.environ["F5_AI_GUARDRAILS_SCAN_PROMPT"] = ""  # Empty string = False
        importlib.reload(main)
        
        client_new = client.__class__(main.app)
        
        setup_mock_chat_completion()
        
        response = client_new.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False
            }
        )
        
        assert response.status_code == 200
        # Verify guardrails was not called
        assert len(mock_guardrails.calls) == 0
    
    def test_no_scanning_when_response_scan_disabled(
        self, client, mock_backend, mock_guardrails,
        setup_mock_chat_completion, test_env_vars
    ):
        """Test that no scanning occurs when response scanning is disabled"""
        import importlib
        import main
        
        os.environ["F5_AI_GUARDRAILS_SCAN_RESPONSE"] = ""  # Empty string = False
        importlib.reload(main)
        
        client_new = client.__class__(main.app)
        
        setup_mock_chat_completion()
        
        response = client_new.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False
            }
        )
        
        assert response.status_code == 200
        # Verify guardrails was not called
        assert len(mock_guardrails.calls) == 0
