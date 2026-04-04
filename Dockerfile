# Use Python slim image to keep size low
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Install system dependencies required for lxml and c-extensions
RUN apt-get update && apt-get install -y \
    gcc \
    libxslt-dev \
    libxml2-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements and install them securely
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app files into the container
COPY . .

# Expose the API Port
EXPOSE 8600

# Start Uvicorn to run the FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8600"]
