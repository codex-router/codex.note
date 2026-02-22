FROM python:3.11-slim

WORKDIR /app

# Copy application code
COPY . .

# Default OpenAI-compatible endpoint/model; API key should be provided at runtime
ENV LITELLM_BASE_URL="https://litellm.com/v1"
ENV LITELLM_API_KEY=""
ENV LITELLM_MODEL="ollama-gemini-3-flash-preview"

ENTRYPOINT ["python", "generate_note.py"]
