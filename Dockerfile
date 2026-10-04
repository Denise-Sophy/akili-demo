FROM python:3.12-slim

WORKDIR /app
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt
COPY . .

# Cloud Run / App Runner / Container Apps all inject PORT. Secrets (AKILI_TOKENS,
# AKILI_ALLOWED_HOSTS) come from the platform's secret store, never the image.
ENV PORT=8080
CMD ["sh", "-c", "uvicorn server.akili_mcp_server:app --host 0.0.0.0 --port ${PORT}"]
