ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    jq \
    fonts-inter \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment to avoid system package conflicts
RUN python3 -m venv /opt/frame-dash-venv
ENV PATH="/opt/frame-dash-venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && playwright install --with-deps chromium

# Copy application
COPY frame_dash/ /opt/frame-dash/frame_dash/
COPY run.sh /

RUN chmod +x /run.sh

CMD [ "/run.sh" ]
