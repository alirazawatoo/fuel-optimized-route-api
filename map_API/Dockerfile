FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --create-home --uid 1000 app
USER app

EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py load_fuel_data && python manage.py runserver 0.0.0.0:8000"]
