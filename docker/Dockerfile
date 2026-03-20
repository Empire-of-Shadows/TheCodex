FROM python:3.13-slim

# Install required system packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    ffmpeg \
    curl \
    procps \
    openssh-client \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Trust GitHub host key
RUN mkdir -p /root/.ssh && \
    ssh-keyscan github.com >> /root/.ssh/known_hosts

# Clone your GitHub repo directly
RUN --mount=type=ssh git clone git@github.com:Empire-of-Shadows/ImperialCodex.git .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create logs directory
RUN mkdir -p logs

# Add environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "codex.py"]
