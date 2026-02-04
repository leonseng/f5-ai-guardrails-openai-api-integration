# Copilot Instructions

## Python Environment

**ALWAYS** use the Python binary from the virtual environment when running Python commands:

- Use `.venv/bin/python` or `.venv/bin/python3` instead of `python` or `python3`
- Use `.venv/bin/pip` instead of `pip`
- Use `.venv/bin/pytest` instead of `pytest`

Example:
```bash
# ✅ Correct
.venv/bin/python -m pytest tests/

# ❌ Incorrect
python -m pytest tests/
python3 -m pytest tests/
```

This ensures all commands use the correct dependencies installed in the virtual environment.
