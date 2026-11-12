# LeaveDesk API image (Capstone 2).
FROM python:3.12-slim

# No .pyc files, unbuffered logs, smaller pip layers.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install libraries first: this layer is reused until requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Then copy only the application code (tests and dev tools stay out of the image).
COPY leavedesk ./leavedesk

# Run as an ordinary user, not root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "leavedesk.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
