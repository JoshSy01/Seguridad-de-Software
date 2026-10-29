FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . /app/

RUN adduser --disabled-password --gecos "" appuser && \
    rm -rf /app/core/migrations && \
    mkdir -p /app/core/migrations && \
    touch /app/core/migrations/__init__.py && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["sh", "-c", "python manage.py makemigrations core --noinput && python manage.py migrate --fake-initial --noinput && python manage.py createcachetable && python manage.py seed_data && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 4"]

