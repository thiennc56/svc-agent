import os

worker_class = "uvicorn.workers.UvicornWorker"
workers = int(os.environ.get("WEB_CONCURRENCY", 2))
worker_connections = 1000
bind = "0.0.0.0:8000"

# Chat stream qua LLM có thể dài → timeout lớn hơn mặc định
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 180))
graceful_timeout = 30
keepalive = 5
preload_app = True

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
access_log_format = '%(h)s %(t)s "%(r)s" %(s)s %(b)s %(D)s'
