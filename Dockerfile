FROM python:3.10-slim-buster

# Set the working directory
WORKDIR /app

# Copy application files
COPY . /app/
COPY .env /app/.env

# Install dependencies
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install netcat-traditional -y 
# && apt-get install tk8.6-dev -y
RUN rm -rf /var/lib/apt/lists/*
# Copy entrypoint script and give execution permissions
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose the application port
EXPOSE 8000

# Set entrypoint script
ENTRYPOINT ["/entrypoint.sh"]
