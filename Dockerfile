FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render maps its own $PORT to whatever we bind to (see keep_alive.py / config.py).
EXPOSE 1000

CMD ["python", "bot.py"]
