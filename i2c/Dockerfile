# Use Torizon base image for ARM64
FROM --platform=linux/arm64/v8 torizon/debian:4 AS deploy

# Install python3-venv, build tools, and i2c-tools
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3-venv \
    gcc \
    python3-dev \
    i2c-tools \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Create and activate virtual environment
RUN python3 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Upgrade pip and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy Python script
COPY i2c_read.py .

# Command to run the script
CMD ["python", "i2c_read.py"]