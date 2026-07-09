#!/bin/bash

set -e

echo "========================================="
echo " Building Notifinho Development Image"
echo "========================================="

docker build \
    -f Dockerfile.dev \
    -t notifinho-dev:local \
    .

echo
echo "Restarting development container..."

docker restart notifinho-dev

echo
echo "✅ Development environment updated."
