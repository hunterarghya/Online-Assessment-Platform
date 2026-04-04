# FROM python:3.10-slim
# ENV PYTHONDONTWRITEBYTECODE 1
# ENV PYTHONUNBUFFERED 1
# WORKDIR /app
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt
# COPY . .
# EXPOSE 8000

# # FROM python:3.10-slim

# # ENV PYTHONDONTWRITEBYTECODE 1
# # ENV PYTHONUNBUFFERED 1

# # WORKDIR /app

# # # 1. Create the sandbox user immediately
# # RUN useradd -m sandboxuser

# # COPY requirements.txt .
# # RUN pip install --no-cache-dir -r requirements.txt

# # COPY . .

# # # 2. SECURITY: 
# # # Make sure the app directory is owned by root 
# # # and NOT readable by the sandboxuser
# # RUN chown -R root:root /app && chmod 755 /app
# # # Allow sandboxuser to write to /tmp for their code execution
# # RUN chmod 1777 /tmp

# # EXPOSE 8000

FROM python:3.10-slim
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
WORKDIR /app

# Install dependencies for psycopg2 and start script
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /app/start.sh

EXPOSE 8000
CMD ["/app/start.sh"]