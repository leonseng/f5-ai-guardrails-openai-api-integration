#!/bin/bash

# Simple test runner script
# Usage: ./run_tests.sh

set -e

echo "Running integration tests..."
.venv/bin/python -m pytest tests/ -v

echo ""
echo "✅ All tests passed!"
