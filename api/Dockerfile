
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

COPY ./req.txt .

RUN pip install --no-cache-dir --upgrade -r req.txt

ENV PYTHONPATH=/app:/database

COPY ./api ./api
COPY ./database ./database
COPY ./worker ./worker
COPY ./parser ./parser
COPY ./ml/model ./ml/model

CMD ["fastapi", "run", "api/main.py", "--port", "80"]