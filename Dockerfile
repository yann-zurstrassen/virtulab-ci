FROM ubuntu:24.04

RUN apt-get update && apt-get install -y \
    gcc-arm-none-eabi \
    gdb-multiarch \
    qemu-system-arm \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
