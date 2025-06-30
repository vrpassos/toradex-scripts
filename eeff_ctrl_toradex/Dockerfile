# Use Torizon base image for ARM64
FROM --platform=linux/arm64/v8 torizon/debian:4 AS deploy

# Install python3-venv and build tools
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3-minimal \
    python3-pip \
    python3-venv \
    build-essential \
    # Remova libgpiod-dev e python3-dev se for instalar via apt para python-gpiod,
    # pois o pacote python3-gpiod já deve trazer suas dependências
    libgpiod-dev \
    python3-dev && \ 
    apt-get clean && apt-get autoremove && \
    rm -rf /var/lib/apt/lists/*

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
COPY eeff_ctrl_toradex.py .

# Command to run the script
CMD ["python3", "eeff_ctrl_toradex.py"] # Use python3 explicitamente