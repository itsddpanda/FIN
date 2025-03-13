FROM python:3.10-slim-buster

# Set the working directory
WORKDIR /app

# Copy application files
COPY . /app/
COPY .env /app/.env
COPY check_log.sh /app/check_log.sh
# Copy crontab file
COPY crontab /etc/cron.d/log-check-cron

# Install dependencies
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install cron zip netcat-traditional -y 

#remove extra files
RUN rm -rf /var/lib/apt/lists/*

# Copy entrypoint script and give execution permissions
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
RUN chmod +x /app/check_log.sh
RUN chmod 0644 /etc/cron.d/log-check-cron
RUN crontab /etc/cron.d/log-check-cron

# Start cron service and the main app
CMD cron && tail -f /dev/null
# Expose the application port
EXPOSE 8000

# Set entrypoint script
ENTRYPOINT ["/entrypoint.sh"]
