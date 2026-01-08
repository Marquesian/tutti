# Docker image for Tutti with static files baked in.
#
# Static files are handled by WhiteNoise. Media files are stored in /app/media,
# so that folder should be mounted as a Docker volume.
#
# The default command runs the gunicorn server on port 8000. You need to run
# migrate yourself, e.g. using `docker run tutti python manage.py migrate
# --noinput`.
FROM python:3.11.14

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app/src

RUN pip install --no-cache-dir gunicorn==23.0.0 psycopg==3.2.10
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Setup static and media folders
ENV DJANGO_STATIC_ROOT=/app/static DJANGO_MEDIA_ROOT=/app/media DJANGO_SECRET_KEY=dummy DJANGO_WHITENOISE=1
RUN mkdir /app/static /app/media && python manage.py collectstatic --noinput
ENV DJANGO_SECRET_KEY=''

# Create user
RUN useradd -u 1001 appuser && chown appuser /app/media
USER appuser

# The SHA1 hash of the commit
ARG SOURCE_COMMIT
ENV SOURCE_COMMIT=$SOURCE_COMMIT

# By default launch gunicorn on :8000
CMD ["gunicorn", "-w", "3", "-b", "0.0.0.0:8000", "tutti.wsgi"]
