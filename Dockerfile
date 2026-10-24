FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY web ./web
RUN pip install --no-cache-dir ".[api,llm]"

ENV WHYITMATTERS_WEB=/app/web
EXPOSE 8000
CMD ["uvicorn", "whyitmatters.api:app", "--host", "0.0.0.0", "--port", "8000"]
