FROM python:3.12-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .

# Expose port
EXPOSE 8000

# Run the application with shell to handle $PORT variable
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
