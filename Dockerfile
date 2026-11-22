# Dockerfile to run Restaurant Intelligence project with Streamlit
# Base image with Python 3.13 (or latest 3.x) slim
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Copy only necessary files first to leverage layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Expose Streamlit default port
EXPOSE 8501

# Default command: activate venv (not needed as we install globally) and run Streamlit app
CMD ["streamlit", "run", "scripts/app.py", "--server.port", "8501", "--server.headless", "true"]
