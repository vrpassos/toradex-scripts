# Use Torizon base image for ARM64
FROM --platform=linux/arm64/v8 torizon/debian:4 AS deploy

# Install python3-venv and build tools (though not strictly needed for this simple script, good practice)
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3-venv \
    # gcc \ # Not strictly needed for a simple Python script
    # python3-dev \ # Not strictly needed for a simple Python script
    # i2c-tools \ # Not needed for UART communication
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
COPY uart_toradex.py .

# Command to run the script
CMD ["python", "uart_toradex.py"]