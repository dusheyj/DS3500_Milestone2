FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# panel serves on 5006 by default
EXPOSE 5006

# --address 0.0.0.0 so docker can forward the port
# --allow-websocket-origin=* so the interactive widgets actually work
CMD ["panel", "serve", "dashboard.py", "--address", "0.0.0.0", "--port", "5006", "--allow-websocket-origin=*"]
