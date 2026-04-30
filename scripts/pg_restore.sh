#!/bin/bash

set -e

# Capture the backup file from the first argument
BACKUP_FILE="$1"

if [ -f ".env" ]; then
    # Export variables so they are available to child processes (like docker compose)
    set -a
    source .env
    set +a
else
    echo "Error: .env not found. Please ensure it is in the same directory."
    exit 1
fi

# Log the environment variables that should be set before docker exec
echo "pg_restore.sh env check: POSTGRES_USER='${POSTGRES_USER}', POSTGRES_DB='${POSTGRES_DB}', POSTGRES_PASSWORD='${POSTGRES_PASSWORD}'"

if [ -z "$POSTGRES_USER" ] || [ -z "$POSTGRES_DB" ] || [ -z "$POSTGRES_PASSWORD" ]; then
    echo "Error: Essential PostgreSQL environment variables (POSTGRES_USER, POSTGRES_DB, POSTGRES_PASSWORD) not set after sourcing .env."
    echo "Please check your .env file and ensure these variables are defined."
    exit 1
fi

if [ -z "$BACKUP_FILE" ]; then
    echo "Error: No backup file specified."
    echo "Usage: ./scripts/pg_restore.sh <path_to_backup_file>"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file '${BACKUP_FILE}' does not exist."
    exit 1
fi

POSTGRES_CONTAINER_NAME=$(docker compose ps -q db)

if [ -z "$POSTGRES_CONTAINER_NAME" ]; then
    echo "Error: Could not find the PostgreSQL container name. Ensure docker compose is running and 'db' service is defined."
    exit 1
fi

echo "Restoring database to container: ${POSTGRES_CONTAINER_NAME}..."

CONTAINER_BACKUP_FILENAME=$(basename "$BACKUP_FILE")
CONTAINER_BACKUP_PATH="/backups/${CONTAINER_BACKUP_FILENAME}"

echo "Using pg_restore command inside the container..."

# Disable set -e to capture exit code of docker exec
set +e
RESTORE_OUTPUT=$(docker exec \
    -e PGPASSWORD=${POSTGRES_PASSWORD} \
    -e POSTGRES_USER=${POSTGRES_USER} \
    -e POSTGRES_DB=${POSTGRES_DB} \
    ${POSTGRES_CONTAINER_NAME} \
    pg_restore -v --dbname=${POSTGRES_DB} --host=localhost --username=${POSTGRES_USER} --clean --if-exists --no-owner --no-acl --single-transaction "${CONTAINER_BACKUP_PATH}" 2>&1)
EXIT_CODE=$?
set -e

if [ $EXIT_CODE -eq 0 ]; then
    echo "Database restore command executed successfully."
    if [ -n "$RESTORE_OUTPUT" ]; then
        echo "--- Restore Output ---"
        echo "$RESTORE_OUTPUT"
        echo "----------------------"
    fi
    echo "Database restore completed successfully from ${BACKUP_FILE}"
else
    echo "Database restore failed."
    echo "--- Restore Output ---"
    echo "$RESTORE_OUTPUT"
    echo "----------------------"
    # Attempt to identify potential database not found error
    if echo "$RESTORE_OUTPUT" | grep -q "database \"${POSTGRES_DB}\" does not exist"; then
        echo "Hint: The database '${POSTGRES_DB}' may not exist. Ensure PostgreSQL initialized correctly."
        echo "Try running 'make recreate-and-start' before 'make restore-db'."
    fi
    exit 1
fi
