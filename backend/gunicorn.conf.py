import os

bind = f"0.0.0.0:{os.environ.get('PORT', 5001)}"
workers = 1
worker_class = "gthread"  # threaded sync worker — no gevent, no recursion issues
threads = 4  # handles concurrent SSE + API requests
timeout = 120
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
