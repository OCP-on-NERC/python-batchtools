#!/usr/bin/env bash
set -euo pipefail

export ORG="${ORG:-memalhot}"
export IMAGE_NAME="${IMAGE_NAME:-csw-dev-test}"
export TAG="${TAG:-latest}"

IMAGE="quay.io/${ORG}/${IMAGE_NAME}:${TAG}"

# Jupyter defaults
CONTAINER_PORT="${CONTAINER_PORT:-8888}"
HOST_PORT="${HOST_PORT:-8888}"

cmd="${1:-}"

case "$cmd" in
  build|"")
    docker build -f Dockerfile.dev -t "$IMAGE" .
    ;;
  push)
    docker push "$IMAGE"
    ;;
  buildpush)
    docker build -f Dockerfile.dev -t "$IMAGE" .
    docker push "$IMAGE"
    ;;
  run)
    docker run --rm -it \
      -p "${HOST_PORT}:${CONTAINER_PORT}" \
      "$IMAGE"
    ;;
  run-hostnet)
    docker run --rm -it --network host "$IMAGE"
    ;;
  *)
    echo "Usage: $0 {build|push|buildpush|run|run-hostnet}"
    echo "Env: ORG IMAGE_NAME TAG HOST_PORT CONTAINER_PORT"
    exit 2
    ;;
esac


#docker run --rm -it -p 8888:8888 a2969a46eebd
