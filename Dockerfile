# always check if Python Slim repo is updated
FROM python:3.9-slim-bookworm

# Set the working directory
WORKDIR /app

# Copy application files
COPY . /app

# install os dependencies
RUN apt-get update && apt-get install -y netcat-traditional && rm -rf /var/lib/apt/lists/*

# Install dependencies
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
# Copy entrypoint script and give execution permissions
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose the application port
EXPOSE 8000

# Set entrypoint script
ENTRYPOINT ["/entrypoint.sh"]
