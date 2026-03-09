ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    jq \
    fonts-inter \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install Python dependencies via uv into a managed venv
COPY pyproject.toml uv.lock /opt/frame-dash/
RUN cd /opt/frame-dash && uv sync --frozen --no-dev \
    && uv run playwright install --with-deps chromium

ENV PATH="/opt/frame-dash/.venv/bin:$PATH"

# Copy application
COPY frame_dash/ /opt/frame-dash/frame_dash/
WORKDIR /opt/frame-dash
COPY run.sh /

RUN chmod +x /run.sh

CMD [ "/run.sh" ]
