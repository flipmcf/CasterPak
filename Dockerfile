## TODO, move into 'casterpak' subdir and update docker-compose.yml accordingly

# --- Stage 1: The Bento4 Extractor ---
FROM alpine:latest AS bento-builder
RUN apk add --no-cache curl unzip
WORKDIR /tmp

# Using the stable 1.6.0 Linux 64-bit binaries of Bento4
RUN curl -O https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip \
    && unzip Bento4-SDK-*.zip \
    && mkdir -p /opt/bento4 \
    && mv Bento4-SDK-*/bin /opt/bento4/bin
    
# --- Stage 2: The Final Application ---  this is what's in the image
# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Install critical system dependencies (minimal)
# libstdc++6 is required for Bento4 binaries to run on Debian/Slim
RUN apt-get update && apt-get install -y \
    sqlite3 \
    libstdc++6 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy Bento4 binaries from the builder stage
COPY --from=bento-builder /opt/bento4/bin /usr/local/bin

# Setup non-root user for security (Best Practice)
RUN adduser --disabled-password --gecos "" casteruser
WORKDIR /app

# Install Python dependencies as a layer before copying source code for better caching
COPY requirements.txt .

# Install the dependencies defined in setup.py
# The "." tells pip to install the current directory as a package
RUN pip install -r requirements.txt

#  Copy application source
COPY . .

## Create input cache directory and grant permissions
## TODO: this path is (for some reason) configurable in config.ini.  Hard-Code it.
RUN mkdir -p /tmp/video_input && chown casteruser /tmp/video_input

#  Create log files for casterpak and grant permissions
RUN touch /var/log/casterpak.error.log && chown casteruser /var/log/casterpak.error.log
RUN touch /var/log/casterpak.access.log && chown casteruser /var/log/casterpak.access.log
RUN touch /var/log/casterpak.cache.log && chown casteruser /var/log/casterpak.cache.log


#  Set internal container environment defaults
# These can be overridden by your docker-compose or ECS task def
ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1
ENV BINARY_PATH=/usr/local/bin
ENV CASTERPAK_BENTO4_BINARYPATH=/usr/local/bin

#  Final setup
RUN chown -R casteruser:casteruser /app
USER casteruser

EXPOSE 5000

# Using Gunicorn for production-grade serving
CMD ["/bin/bash", "run.sh"]
