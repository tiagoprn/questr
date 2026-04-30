#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Source the environment variables from the .env file
# This ensures we have access to POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB
# This script is intended to be run from the host, and requires docker to be available.
if [ -f ".env" ]; then
    source .env
else
    echo "Error: .env not found. Please ensure it is in the same directory."
    exit 1
fi

# Get the container name of the postgres service from docker-compose.yml
POSTGRES_CONTAINER_NAME=$(docker compose ps -q db)

if [ -z "$POSTGRES_CONTAINER_NAME" ]; then
    echo "Error: Could not find the PostgreSQL container name. Ensure docker compose is running and 'db' service is defined."
    exit 1
fi

# Ensure the backups directory exists on the host
mkdir -p backups

# Define the backup directory INSIDE the container, mapped by docker-compose
# This path is where the script *expects* the backup to be written *by the container's pg_dump*
CONTAINER_BACKUP_DIR="/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
# Changed extension to .dump to indicate binary custom format
BACKUP_FILENAME="questr_db_backup_${TIMESTAMP}.dump"
HOST_BACKUP_PATH="./backups/${BACKUP_FILENAME}" # Path on the host

echo "Starting database backup using container: ${POSTGRES_CONTAINER_NAME}..."
echo "Backup will be saved to host at: ${HOST_BACKUP_PATH}"

echo "Running pg_dump through docker exec..."
# Use docker exec to run pg_dump inside the postgres container.
# The output is redirected to stdout, which is then piped to the host file via the shell redirection.
# Added -F c to produce a Custom-format archive, which is required for pg_restore to work correctly.
PGPASSWORD=${POSTGRES_PASSWORD} docker exec \
    -e PGPASSWORD=${POSTGRES_PASSWORD} \
    -e POSTGRES_USER=${POSTGRES_USER} \
    -e POSTGRES_DB=${POSTGRES_DB} \
    ${POSTGRES_CONTAINER_NAME} \
    pg_dump -F c -h localhost -U ${POSTGRES_USER} -d ${POSTGRES_DB} --clean --if-exists --no-owner --no-acl >"${HOST_BACKUP_PATH}"

if [ $? -eq 0 ]; then
    echo "Database backup completed successfully: ${HOST_BACKUP_PATH}"
else
    echo "Database backup failed."
    exit 1
fi
