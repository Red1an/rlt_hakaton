
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

COPY ./req.txt .

RUN pip install --no-cache-dir --upgrade -r req.txt

ENV PYTHONPATH=/app:/database

COPY ./api .
COPY ./database ./database
COPY ./search ./search
COPY ./worker ./worker
COPY ./ml/model ./ml/model

CMD ["fastapi", "run", "main.py", "--port", "80"]