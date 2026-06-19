FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p uploads

ENV FLASK_SECRET_KEY=please-set-in-orchestrator

EXPOSE 8080

CMD ["waitress-serve", "--host=0.0.0.0", "--port=8080", "wsgi:app"]
