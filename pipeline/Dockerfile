FROM python:3.11-slim
WORKDIR /app
COPY pipeline/requirements.txt pipeline/requirements.lock /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*
COPY pipeline /app/pipeline
COPY public/data /app/public/data
CMD ["python", "-m", "pytest", "pipeline/tests", "-q"]
