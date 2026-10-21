FROM python:3.11-slim

WORKDIR /app

# Optional build arg: set to "1" to compile pysqlcipher3 for DB_ENCRYPTION_KEY support.
# Example: docker build --build-arg ENABLE_SQLCIPHER=1 .
ARG ENABLE_SQLCIPHER=0

COPY requirements.txt .

RUN if [ "$ENABLE_SQLCIPHER" = "1" ]; then \
      apt-get update && apt-get install -y --no-install-recommends \
        libsqlcipher-dev gcc && \
      rm -rf /var/lib/apt/lists/* && \
      pip install --no-cache-dir pysqlcipher3==1.2.1; \
    fi

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

VOLUME ["/data"]

EXPOSE 8096

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8096"]
