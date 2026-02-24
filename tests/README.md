# Integration Tests

This directory contains comprehensive integration tests for the OpenAI API proxy with F5 AI Guardrails integration.

## Overview

The test suite uses **mocked backends** for fast, reliable testing without external dependencies:
- **Mock OpenAI-compatible backend** - Using respx to mock HTTP responses
- **Mock F5 AI Guardrails** - Using respx to mock guardrails API with schema matching the real API

All tests run locally without requiring real services like Ollama, OpenAI, or F5 Guardrails.

### Mock API Accuracy

The guardrails mock (`tests/mocks/guardrails_mock.py`) accurately reflects the real F5 AI Guardrails API schema, including:
- Top-level `id` field
- Nested `result` object with `scannerResults` array and `outcome` field
- `redactedInput` field (when outcome is "redacted")
- Realistic scanner metadata and timestamps

This ensures tests remain valid even as the code evolves to use additional API fields.

## Test Organization

```
tests/
├── README.md                        # This file
├── conftest.py                      # Pytest fixtures and configuration
├── test_chat_completions.py         # Chat completion endpoint tests
├── test_guardrails_integration.py   # Guardrails integration tests
├── test_models.py                   # Models endpoint tests
├── test_e2e_scenarios.py            # End-to-end scenario tests
└── mocks/
    ├── __init__.py
    ├── openai_mock.py               # OpenAI API mocks
    └── guardrails_mock.py           # F5 Guardrails API mocks
```

## Running Tests

### Option 1: Use the Test Runner Script (Easiest)

```bash
./run_tests.sh
```

### Option 2: Activate Virtual Environment (Recommended for development)

```bash
# Activate the virtual environment
source .venv/bin/activate

# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_chat_completions.py

# Run with verbose output
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=main --cov-report=html

# When done, deactivate
deactivate
```

### Option 3: Use Full Path to pytest

```bash
# Run all tests
.venv/bin/python -m pytest tests/

# Run specific test file
.venv/bin/python -m pytest tests/test_chat_completions.py

# Run with verbose output
.venv/bin/python -m pytest tests/ -v

# Run with coverage report
.venv/bin/python -m pytest tests/ --cov=main --cov-report=html
```

## Test Coverage

The test suite covers:

### Chat Completions (`test_chat_completions.py`)
- ✅ Non-streaming chat completions
- ✅ Streaming chat completions
- ✅ System prompt injection
- ✅ Error handling (invalid JSON, backend errors)

### Guardrails Integration (`test_guardrails_integration.py`)
- ✅ Prompt scanning (cleared, flagged, redacted)
- ✅ Response scanning (cleared, flagged, redacted)
- ✅ Redaction enable/disable functionality
- ✅ Streaming and non-streaming modes
- ✅ Guardrails disabled scenarios

### Models Endpoint (`test_models.py`)
- ✅ Models listing with mock backend
- ✅ Error handling

### End-to-End Scenarios (`test_e2e_scenarios.py`)
- ✅ Combined prompt and response redaction
- ✅ Prompt blocked by guardrails
- ✅ Response blocked by guardrails
- ✅ Streaming with both scans enabled
- ✅ Concurrent request handling

## CI/CD Integration

The test suite is perfect for CI/CD pipelines as it requires no external services:

```yaml
# Example GitHub Actions workflow
- name: Install dependencies
  run: pip install -e .[dev]

- name: Run tests
  run: pytest tests/ --cov=main --cov-report=xml

- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    file: ./coverage.xml
```

## Performance

All tests use mocked backends, making them very fast:
- **Typical execution time**: <1 second for full test suite
- **No network calls**: All HTTP requests are mocked
- **No external dependencies**: Works in any environment

## Troubleshooting

### Tests fail with "module reload" errors
This can happen when environment variables change between tests. Solutions:
- Run tests in isolated processes: `pytest tests/ --forked` (requires pytest-forked)
- Clear pytest cache: `pytest --cache-clear`

### Mock not working
- Ensure `respx` is installed: `pip install respx`
- Check that mock fixtures are being used in test function signatures
- Verify the mock URL matches the `OPENAI_API_URL` in test environment

## Contributing

When adding new tests:
1. Follow existing test structure and naming conventions
2. Use appropriate fixtures from `conftest.py`
3. Ensure tests are isolated and don't depend on execution order
4. Add tests to the appropriate test file based on functionality
5. Update this README if adding new test categories
