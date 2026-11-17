# Stage 1: build the React trading screen
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: compile the C++ engine and run the API
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY engine/ engine/
RUN pip install --no-cache-dir ./engine
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
COPY server/ server/
COPY --from=web /web/dist web/dist
ENV EXCHANGE_DB=/data/exchange.db
VOLUME /data
EXPOSE 8000
WORKDIR /app/server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
