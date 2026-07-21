# Use the official Python 3.11 slim image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860

# Install system dependencies (Tesseract OCR, Poppler)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-tur \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Create user to run the application (Hugging Face Spaces requirement)
RUN useradd -m -u 1000 user

# Set working directory and ownership BEFORE switching to user
WORKDIR /app
RUN chown -R 1000:1000 /app

# Switch to the non-root user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

# Copy requirements and install
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY --chown=user:user . .

# Expose port
EXPOSE 7860

# Start FastAPI application with Uvicorn, using the PORT environment variable if available
CMD uvicorn api:app --host 0.0.0.0 --port ${PORT:-7860}
