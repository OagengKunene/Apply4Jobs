FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir . && python -m playwright install --with-deps chromium
ENV APPLYATLAS_DATA_DIR=/app/data
CMD ["applyatlas", "serve"]
