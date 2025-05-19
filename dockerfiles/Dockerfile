# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /home

# Install necessary dependencies
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Install Selenium and Pandas
RUN pip install selenium pandas

# Set environment variables for Chrome driver
ENV DISPLAY=:99
ENV CHROME_BIN=/usr/bin/chromium


