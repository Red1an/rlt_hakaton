
FROM python:3.12-slim

WORKDIR /app

COPY ./req.txt .

RUN pip install --no-cache-dir --upgrade -r req.txt

ENV PYTHONPATH=/app:/database

COPY ./api .
COPY ./database ./database
COPY ./search ./search
COPY ./worker ./worker

CMD ["fastapi", "run", "main.py", "--port", "80"]