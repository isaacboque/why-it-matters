FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY web ./web
RUN pip install --no-cache-dir ".[api,llm,maf]"

ENV WHYITMATTERS_WEB=/app/web \
    WIM_ENGINE=agent_framework \
    WIM_WARM_SEEDS=391,193,51,63,144,194,487,353
EXPOSE 8000
CMD ["uvicorn", "whyitmatters.api:app", "--host", "0.0.0.0", "--port", "8000"]
