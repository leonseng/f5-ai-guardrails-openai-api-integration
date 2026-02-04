# F5 AI Guardrails integration with OpenAI API proxy

This demonstrates how an OpenAI API proxy/LLM orchestration application can be integrated and secured with F5 AI Guardrails via sideband API calls.

![Architecture](./assets/architecture.excalidraw.png)

Notes:
- the app is written in FastAPI, exposing OpenAI API's `/models` and `/chat/completion` endpoints to support connections from frontends such as Open WebUI
- supports both streaming and non-streaming responses
- supports scanning/redaction of both prompts and responses, configured via `F5_AI_GUARDRAILS_SCAN_*` and `F5_AI_GUARDRAILS_REDACT_*` variables in `.env` file

## Quickstart

```
# Create `.env` from `.env.example` and update the values in `.env`
cp .env .env.example

# Build proxy image
docker compose build

# Run the setup
docker compose up
```

Browse to [http://localhost:8080](http://localhost:8080) to access Open WebUI.

Send a prompt and observe scan logs, e.g.
```
DEBUG:    Guardrail scan results: redacted.
```

Confirm scan results on F5 AI Guardrails console.

## Development

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
# Install production + development dependencies
pip install -e .[dev]
```

2. Run the server:

```bash
export OPENAI_API_URL=http://192.168.0.4:11434
uvicorn main:app --host 0.0.0.0 --port 8000
```

3. Example curl (proxying a chat completions request):

```bash
curl -X POST "http://localhost:8000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Hello"}]}'
```

## Testing

The project includes a comprehensive integration test suite using mocked backends for fast, reliable testing.

### Quick Start

**Easiest way - use the test runner script:**

```bash
./run_tests.sh
```

**Or activate the virtual environment:**

```bash
source .venv/bin/activate
pytest tests/
```

**Or use the full path:**

```bash
.venv/bin/python -m pytest tests/
```

### Run with Coverage

```bash
# With test script
./run_tests.sh  # (add coverage flag if needed)

# With venv activated
source .venv/bin/activate
pytest tests/ --cov=main --cov-report=html

# Without venv activated
.venv/bin/python -m pytest tests/ --cov=main --cov-report=html
```

### Key Features

- **Fast**: All tests use mocked backends (~1 second for full suite)
- **No external dependencies**: Works without Ollama, OpenAI, or real F5 Guardrails
- **Comprehensive**: 27 tests covering all functionality
- **CI/CD Ready**: Perfect for automated testing pipelines

See [tests/README.md](tests/README.md) for detailed testing documentation, including:
- Test organization and structure
- Running specific test suites
- Adding new tests
- Troubleshooting
