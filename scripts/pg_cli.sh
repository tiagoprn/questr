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
# hostname, port, user, and database. If it's not in the expected format,
# we construct it manually using localhost and the dynamically found host port.

if [ -n "$DATABASE_URL" ]; then
    # Attempt to parse DATABASE_URL
    # Example: postgres://user:PASSWORD@localhost:5432/questr_db?sslmode=disable
    parsed_url=$(echo "$DATABASE_URL" | sed -n 's|^postgres://\([^:]*\):\([^@]*\)@\([^:]*\):\([0-9]*\)/\(.*?\)|\1:\2:\3:\4:\5|p')

    if [ -n "$parsed_url" ]; then
        # If parsing was successful, extract parts
        POSTGRES_USER=$(echo "$parsed_url" | cut -d: -f1)
        POSTGRES_PASSWORD=$(echo "$parsed_url" | cut -d: -f2)
        POSTGRES_HOST=$(echo "$parsed_url" | cut -d: -f3)
        POSTGRES_PORT=$(echo "$parsed_url" | cut -d: -f4)
        POSTGRES_DB=$(echo "$parsed_url" | cut -d: -f5)

        # Ensure host is localhost as requested
        POSTGRES_HOST="localhost"

        # Reconstruct connection string with explicit localhost and port
        # Ensure sslmode is handled if present, otherwise default to disable.
        SSLMODE=$(echo "$DATABASE_URL" | sed -n 's/.*sslmode=\([^& ]*\).*/\1/p')
        if [ -z "$SSLMODE" ]; then
            SSLMODE="disable"
        fi
        CONNECTION_URL="postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}?sslmode=${SSLMODE}"

    else
        # Fallback if DATABASE_URL is not in the expected format
        echo "Warning: DATABASE_URL in .env is not in the expected 'postgres://user:pass@host:port/dbname' format. Falling back to manual construction."
        POSTGRES_HOST="localhost"
        # Find the host port mapping for the db service
        POSTGRES_HOST_PORT=$(docker compose port db 5432 | sed 's/.*://')

        if [ -z "$POSTGRES_HOST_PORT" ]; then
            echo "Error: Could not determine PostgreSQL host and port."
            echo "Please ensure DATABASE_URL is set correctly in .env or the 'db' service in docker-compose.yml publishes port 5432."
            exit 1
        fi
        # Use the individual environment variables if DATABASE_URL parsing failed
        CONNECTION_URL="postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_HOST_PORT}/${POSTGRES_DB}?sslmode=disable"
    fi
else
    # Fallback if DATABASE_URL is not defined at all
    echo "Warning: DATABASE_URL not found in .env. Constructing connection string from individual variables."
    POSTGRES_HOST="localhost"
    # Find the host port mapping for the db service
    POSTGRES_HOST_PORT=$(docker compose port db 5432 | sed 's/.*://')

    if [ -z "$POSTGRES_HOST_PORT" ]; then
        echo "Error: Could not determine PostgreSQL host and port."
        echo "Please ensure 'db' service in docker-compose.yml publishes port 5432."
        exit 1
    fi
    CONNECTION_URL="postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_HOST_PORT}/${POSTGRES_DB}?sslmode=disable"
fi

echo "Connecting to PostgreSQL via pgcli using connection string... ($CONNECTION_URL)"

# Execute pgcli with the connection string
pgcli "${CONNECTION_URL}"

echo "pgcli session ended."
