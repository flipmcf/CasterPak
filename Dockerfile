# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED 1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install Bento4
RUN curl -o bento4.zip https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip && \
    unzip bento4.zip && \
    cp Bento4-SDK-1-6-0-641.x86_64-unknown-linux/bin/* /usr/local/bin/ && \
    rm -rf bento4.zip Bento4-SDK-1.6.0-640.x86_64-unknown-linux

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . .

# Install any needed packages specified in setup.py
RUN pip install .

#
# A config.ini file is required. It is recommended to mount it as a volume at runtime.
# For example:
# docker run -v /path/to/your/config.ini:/app/config.ini casterpak
#
# You can create your config.ini from the provided config_example.ini
#

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Run the app.
CMD ["gunicorn", "--config", "gunicorn.conf.py", "-b", "0.0.0.0:5000", "wsgi:app"]
