FROM python:3.12-slim

# PostgreSQL runtime libs (für psycopg2-binary nicht zwingend, aber sicher)
RUN apt-get update && apt-get install -y libpq5 && apt-get clean

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["python", "app.py"]
