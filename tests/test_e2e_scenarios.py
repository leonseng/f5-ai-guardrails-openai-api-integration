import os
import json


class TestEndToEndScenarios:
    """Test end-to-end scenarios combining multiple features"""
    
    def test_prompt_and_response_redaction(
        self, client, mock_backend, mock_guardrails,
        setup_mock_chat_completion, test_env_vars
    ):
        """Test complete flow with both prompt and response redaction"""
        import importlib
        import main
        from httpx import Response
        
        os.environ["F5_AI_GUARDRAILS_SCAN_PROMPT"] = "true"
        os.environ["F5_AI_GUARDRAILS_SCAN_RESPONSE"] = "true"
        os.environ["F5_AI_GUARDRAILS_REDACT_PROMPT"] = "true"
        os.environ["F5_AI_GUARDRAILS_REDACT_RESPONSE"] = "true"
        importlib.reload(main)
        
        client_new = client.__class__(main.app)
        
        # Setup mocks
        setup_mock_chat_completion(response_text="Response with SSN: 987-65-4321")
        
        # Mock prompt scan (redacted)
        from tests.mocks.guardrails_mock import create_redacted_response
        mock_guardrails.post("/api/scans").mock(
            side_effect=[
                Response(
                    status_code=200,
                    json=create_redacted_response(
                        "Prompt with SSN: 123-45-6789",
                        "Prompt with SSN: [REDACTED]"
                    )
                ),
                Response(
                    status_code=200,
                    json=create_redacted_response(
                        "Response with SSN: 987-65-4321",
                        "Response with SSN: [REDACTED]"
                    )
                )
            ]
        )
        
        response = client_new.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Prompt with SSN: 123-45-6789"}],
                "stream": False
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response was redacted
        assert data["choices"][0]["message"]["content"] == "Response with SSN: [REDACTED]"
        
        # Verify prompt was redacted when sent to backend
        backend_request = mock_backend.calls.last.request
        backend_body = json.loads(backend_request.content)
        assert backend_body["messages"][-1]["content"] == "Prompt with SSN: [REDACTED]"
    
    def test_prompt_blocked_scenario(
        self, client, mock_backend, mock_guardrails,
        test_env_vars
    ):
        """Test complete flow where prompt is blocked by guardrails"""
        import importlib
        import main
        from httpx import Response
        from tests.mocks.guardrails_mock import create_flagged_response
        
        os.environ["F5_AI_GUARDRAILS_SCAN_PROMPT"] = "true"
        importlib.reload(main)
        
        client_new = client.__class__(main.app)
        
        # Mock prompt scan (flagged)
        mock_guardrails.post("/api/scans").mock(
            return_value=Response(
                status_code=200,
                json=create_flagged_response("Inappropriate content")
            )
        )
        
        response = client_new.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Inappropriate content"}],
                "stream": False
            }
        )
        
        assert response.status_code == 400
        assert "Prompt blocked by Guardrail" in response.text
        
        # Verify backend was never called
        assert len(mock_backend.calls) == 0
    
    def test_response_blocked_scenario(
        self, client, mock_backend, mock_guardrails,
        setup_mock_chat_completion, test_env_vars
    ):
        """Test complete flow where response is blocked by guardrails"""
        import importlib
        import main
        from httpx import Response
        from tests.mocks.guardrails_mock import create_flagged_response, create_cleared_response
        
        # Only enable response scanning
        os.environ["F5_AI_GUARDRAILS_SCAN_PROMPT"] = ""  # Disabled
        os.environ["F5_AI_GUARDRAILS_SCAN_RESPONSE"] = "true"
        importlib.reload(main)
        
        client_new = client.__class__(main.app)
        
        # Setup backend mock
        setup_mock_chat_completion(response_text="Unsafe response content")
        
        # Mock response scan (flagged)
        mock_guardrails.post("/api/scans").mock(
            return_value=Response(
                status_code=200,
                json=create_flagged_response("Unsafe response content")
            )
        )
        
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
    
    def test_streaming_with_both_scans_enabled(
        self, client, mock_backend, mock_guardrails,
        setup_mock_chat_completion, setup_mock_guardrails_scan,
        test_env_vars
    ):
        """Test streaming mode with both prompt and response scanning enabled"""
        import importlib
        import main
        from httpx import Response
        from tests.mocks.guardrails_mock import create_cleared_response
        
        os.environ["F5_AI_GUARDRAILS_SCAN_PROMPT"] = "true"
        os.environ["F5_AI_GUARDRAILS_SCAN_RESPONSE"] = "true"
        importlib.reload(main)
        
        client_new = client.__class__(main.app)
        
        # Setup backend mock for streaming
        setup_mock_chat_completion(response_text="Hello! How can I help?", streaming=True)
        
        # Mock both scans as cleared
        mock_guardrails.post("/api/scans").mock(
            side_effect=[
                Response(
                    status_code=200,
                    json=create_cleared_response("Hello")
                ),
                Response(
                    status_code=200,
                    json=create_cleared_response("Hello! How can I help?")
                )
            ]
        )
        
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
        
        # Verify streaming response contains content
        content = response.text
        assert "Hello" in content
        assert "[DONE]" in content
    
    def test_concurrent_requests(
        self, client, mock_backend, mock_guardrails,
        setup_mock_chat_completion, setup_mock_guardrails_scan,
        test_env_vars
    ):
        """Test handling of concurrent requests"""
        import importlib
        import main
        import asyncio
        from httpx import AsyncClient, ASGITransport
        
        os.environ["F5_AI_GUARDRAILS_SCAN_PROMPT"] = "true"
        importlib.reload(main)
        
        setup_mock_chat_completion()
        setup_mock_guardrails_scan(outcome="cleared", input_text="Hello")
        
        async def make_request():
            transport = ASGITransport(app=main.app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post(
                    "/v1/chat/completions",
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": "Hello"}],
                        "stream": False
                    }
                )
                return response.status_code
        
        # Make multiple concurrent requests
        async def run_concurrent():
            tasks = [make_request() for _ in range(5)]
            results = await asyncio.gather(*tasks)
            return results
        
        results = asyncio.run(run_concurrent())
        
        # All requests should succeed
        assert all(status == 200 for status in results)
