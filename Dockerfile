# === Python-Dockerfile für Krankenhausnetz mit internen CAs ===
FROM python:3.12-slim

# PostgreSQL runtime libs + CA utilities
RUN apt-get update && \
    apt-get install -y libpq5 ca-certificates && \
    apt-get clean

# Proxy für Build & Runtime
ARG http_proxy
ARG https_proxy
ARG no_proxy
ENV HTTP_PROXY=${http_proxy}
ENV HTTPS_PROXY=${https_proxy}
ENV NO_PROXY=${no_proxy}

WORKDIR /app

# Requirements installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Quellcode kopieren
COPY . .

EXPOSE 8000
CMD ["python", "app.py"]
