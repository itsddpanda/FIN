FROM python:3.9-slim-buster

# Set the working directory
WORKDIR /app

# Copy application files
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy entrypoint script and give execution permissions
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose the application port
EXPOSE 8000

# Set entrypoint script
ENTRYPOINT ["/entrypoint.sh"]
