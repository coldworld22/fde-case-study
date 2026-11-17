FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install ".[postgres]"

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 app
COPY --from=build /install /usr/local
USER app
WORKDIR /home/app
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')"
CMD ["uvicorn", "clinicbot.app:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
