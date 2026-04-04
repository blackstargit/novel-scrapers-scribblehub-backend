# Use Python slim image to keep size low
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Install system dependencies required for lxml and C-extensions
RUN apt-get update && apt-get install -y \
    gcc \
    libxslt-dev \
    libxml2-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements and install them first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Expose the API port
EXPOSE 8600

# Start Uvicorn — entry point is now app/main.py (package style)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8600"]
