# Use the official Python image
FROM python:3.11-slim-bookworm

# Set working directory
WORKDIR /app

# Install system dependencies (like Java for Spark if needed)
RUN apt-get update && apt-get install -y default-jre

#Allows it to communicate with the MYSQL service
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN pip install mysqlclient

#SPARK IS INSTALLED SOLELY SO THAT THE COMMAND IS RECOGNIZED
#SPARK IS NOT RUN HERE
# 1. Install a minimal JRE (required for Spark)
RUN apt-get update && \
    apt-get install -y --no-install-recommends default-jre && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 2. Install PySpark
RUN pip install --no-cache-dir pyspark==3.5.8

# Install Docker CLI so the backend can scale containers
RUN apt-get update && apt-get install -y docker.io

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Run the server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
