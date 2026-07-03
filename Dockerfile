# ============================================================
# Stage 1 – dependency builder
# ============================================================
FROM python:3.12-slim AS builder

# Prevent .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install build-time OS deps (needed for some Python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a local prefix so we can
# copy only the installed packages into the final stage
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ============================================================
# Stage 2 – final production image
# ============================================================
FROM python:3.12-slim AS final

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Tell Python where the packages installed in stage 1 live
    PYTHONPATH=/app \
    PATH="/install/bin:$PATH"

# Runtime-only OS deps (libpq for psycopg2, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from the builder stage
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy project source
COPY . .

# Copy and prepare the entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Create a non-root user and hand over ownership
RUN addgroup --system django \
 && adduser --system --ingroup django django \
 && mkdir -p /app/data \
 && chown -R django:django /app \
 && chmod 775 /app/data

USER django

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]