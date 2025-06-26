# Use Torizon base image for ARM64
FROM --platform=linux/arm64/v8 torizon/debian:4 AS deploy

# Atualiza pacotes e instala i2c-tools
RUN apt-get update && \
    apt-get install -y i2c-tools && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Define um shell interativo como comando padrão
CMD ["/bin/bash"]