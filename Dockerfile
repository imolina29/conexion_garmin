FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sync.py analysis.py bot.py users.py calendar_server.py ./

RUN mkdir -p data/raw/activities data/raw/stats

EXPOSE 8080

CMD ["python", "bot.py"]
