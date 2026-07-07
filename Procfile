web: alembic upgrade head && gunicorn src.main:app --bind 0.0.0.0:$PORT --timeout 300 --workers 1 --threads 4 --worker-class gthread
