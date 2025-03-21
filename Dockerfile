FROM python:3.10-slim-buster

# Set the working directory
WORKDIR /app

# Copy application files
COPY . /app/
COPY .env /app/.env

# Install dependencies
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

#remove extra files
RUN rm -rf /var/lib/apt/lists/*

# Expose the application port
EXPOSE 8000

# Set entrypoint script
CMD ["python", "main.py"]