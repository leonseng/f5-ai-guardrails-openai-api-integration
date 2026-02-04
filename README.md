# F5 AI Guardrails integration with OpenAI API proxy

This demonstrates how an OpenAI API proxy/LLM orchestration application can be integrated and secured with F5 AI Guardrails via sideband API calls.

![Architecture](./assets/architecture.excalidraw.png)

Notes:
- the app is written in FastAPI, exposing OpenAI API's `/models` and `/chat/completion` endpoints to support connections from frontends such as Open WebUI
- supports both streaming and non-streaming responses
- supports scanning/redaction of both prompts and responses, configured via `F5_AI_GUARDRAILS_SCAN_*` and `F5_AI_GUARDRAILS_REDACT_*` variables in `.env` file

## Configuration

The application is configured using environment variables. Create a `.env` file based on `.env.example` and configure the following variables:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `OPENAI_API_URL` | Backend OpenAI-compatible API endpoint (e.g., Ollama, OpenAI) | `http://127.0.0.1:11434` | Yes |
| `OPENAI_API_KEY` | API key for authenticating with the backend API. Overrides any Authorization header from the client | None | No |
| `MODEL` | Default model to use for chat completions. Overrides model specified by client | None | No |
| `SYSTEM_PROMPT` | System prompt to inject into conversations that don't already have one | None | No |
| `PROXY_TIMEOUT` | Timeout in seconds for non-streaming requests to the backend | `30` | No |
| `F5_AI_GUARDRAILS_API_URL` | F5 AI Guardrails API endpoint URL | None | Yes (if scanning enabled) |
| `F5_AI_GUARDRAILS_API_TOKEN` | Authentication token for F5 AI Guardrails API | None | Yes (if scanning enabled) |
| `F5_AI_GUARDRAILS_PROJECT_ID` | Project ID in F5 AI Guardrails for organizing scans | None | Yes (if scanning enabled) |
| `F5_AI_GUARDRAILS_SCAN_PROMPT` | Enable scanning of user prompts before sending to backend | `false` | No |
| `F5_AI_GUARDRAILS_SCAN_RESPONSE` | Enable scanning of LLM responses before returning to client | `false` | No |
| `F5_AI_GUARDRAILS_REDACT_PROMPT` | Apply redactions to flagged content in prompts instead of blocking | `false` | No |
| `F5_AI_GUARDRAILS_REDACT_RESPONSE` | Apply redactions to flagged content in responses instead of blocking | `false` | No |

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
