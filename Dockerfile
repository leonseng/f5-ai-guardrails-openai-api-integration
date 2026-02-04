FROM python:3.14-slim

WORKDIR /app

# Install runtime deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy app
COPY . /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
