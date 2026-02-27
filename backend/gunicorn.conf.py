import os

bind = f"0.0.0.0:{os.environ.get('PORT', 5001)}"
workers = 1  # single worker — SSE needs sticky connections
worker_class = "gevent"  # async worker — handles concurrent SSE streams
worker_connections = 100
timeout = 120  # long timeout for Nifty 500 scans
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
