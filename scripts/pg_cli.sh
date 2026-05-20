#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Source the environment variables from the .env file
if [ -f ".env" ]; then
    source .env
else
    echo "Error: .env not found. Please ensure it is in the same directory."
    exit 1
fi

# Check if pgcli is installed. If not, provide instructions.
if ! command -v pgcli &>/dev/null; then
    echo "Error: pgcli could not be found."
    echo "Please install it using: uv pip install pgcli" # or pipx install pgcli
    exit 1
fi

# Construct the connection URL for pgcli.
# We attempt to use the DATABASE_URL from .env, which should contain
CONNECTION_URL="postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:5432/${POSTGRES_DB}?sslmode=disable"

echo "Connecting to PostgreSQL via pgcli using connection string... ($CONNECTION_URL)"

# Execute pgcli with the connection string
pgcli "${CONNECTION_URL}"

echo "pgcli session ended."
