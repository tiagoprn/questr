#!/bin/sh
# Build the production image from deploy/Dockerfile and push both tags to the
# Forgejo registry (D4: semver from pyproject.toml plus :latest).
# Prereqs:
#   - logged in: tmp/container-registry.md B2
#   - run from anywhere (script cds to the repo root)
set -eu

REGISTRY='oa.saga-torino.ts.net:3000'
IMAGE="$REGISTRY/tiago/questr"

cd "$(dirname "$0")/../.."

VERSION="$(uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
echo "==> Building questr version $VERSION"

docker build -f deploy/Dockerfile -t "$IMAGE:$VERSION" -t "$IMAGE:latest" .
docker push "$IMAGE:$VERSION"
docker push "$IMAGE:latest"
echo "==> Pushed $IMAGE:$VERSION and $IMAGE:latest"
