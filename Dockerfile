FROM ubuntu:24.04

ARG TARGETARCH
ARG RENODE_VERSION=1.17.0

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        gcc-arm-none-eabi \
        binutils-arm-none-eabi \
        libnewlib-arm-none-eabi \
        libstdc++-arm-none-eabi-newlib \
        qemu-system-arm \
        python3 \
        git \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    # The toolchain ships newlib/libstdc++ for every Arm profile (~2.5 GB). Keep
    # only the multilibs our boards select (CPU flags in virtulab/boards.py).
    # This must stay in the install layer, or the deleted files still ship.
    && keep=$(for flags in "-mcpu=cortex-m0" "-mcpu=cortex-m3" \
            "-mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=hard" \
            "-mcpu=cortex-m7 -mfpu=fpv5-d16 -mfloat-abi=hard"; do \
            arm-none-eabi-gcc $flags -mthumb -print-multi-directory; done | sort -u) \
    && echo "Keeping multilibs:" $keep \
    && for base in /usr/lib/arm-none-eabi/lib /usr/lib/gcc/arm-none-eabi/*; do \
        rm -rf "$base/arm"; \
        for dir in "$base"/thumb/*/*; do \
            rel="thumb/$(basename "$(dirname "$dir")")/$(basename "$dir")"; \
            echo "$keep" | grep -qx "$rel" || rm -rf "$dir"; \
        done; \
        find "$base/thumb" -mindepth 1 -type d -empty -delete; \
    done

# Renode (self-contained .NET build). Platform descriptions fetch SVD register
# files from the internet at startup; cache them in the image and point the
# platforms at the local copies so emulation works offline.
RUN case "${TARGETARCH:-amd64}" in \
        arm64) asset="linux-arm64-portable" ;; \
        *) asset="linux-portable" ;; \
    esac \
    && curl -fsSL "https://github.com/renode/renode/releases/download/v${RENODE_VERSION}/renode-${RENODE_VERSION}.${asset}.tar.gz" \
        | tar -xz -C /opt \
    && mv /opt/renode_* /opt/renode \
    && ln -s /opt/renode/renode /usr/local/bin/renode \
    && mkdir -p /opt/renode/svd \
    && for svd in STM32F40x; do \
        curl -fsSL -o "/opt/renode/svd/${svd}.svd.gz" "https://dl.antmicro.com/projects/renode/svd/${svd}.svd.gz" \
        && sed -i "s|@https://dl.antmicro.com/projects/renode/svd/${svd}.svd.gz|@/opt/renode/svd/${svd}.svd.gz|" \
            /opt/renode/platforms/cpus/*.repl; \
    done

COPY virtulab /opt/virtulab/virtulab
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
    && printf '#!/bin/sh\nexec python3 -m virtulab "$@"\n' > /usr/local/bin/virtulab \
    && chmod +x /usr/local/bin/virtulab

ENV PYTHONPATH=/opt/virtulab \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 \
    DOTNET_CLI_TELEMETRY_OPTOUT=1

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
