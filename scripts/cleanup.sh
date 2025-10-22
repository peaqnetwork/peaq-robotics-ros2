#!/bin/bash

echo "🧹 Cleaning up Docker containers and images..."

# Stop all peaq-related containers
echo "Stopping containers..."
docker stop peaq-ros2-test ipfsdaemon ipfs-daemon 2>/dev/null || true

# Remove all peaq-related containers
echo "Removing containers..."
docker rm peaq-ros2-test ipfsdaemon ipfs-daemon 2>/dev/null || true

# Remove peaq-ros2 image
echo "Removing image..."
docker rmi peaq-ros2:latest 2>/dev/null || true

# Verify cleanup
echo ""
echo "Checking for remaining containers..."
REMAINING=$(docker ps -a | grep -E "peaq|ipfs" || true)

if [ -z "$REMAINING" ]; then
    echo "✅ Cleanup complete! No peaq or IPFS containers found."
else
    echo "⚠️  Some containers still exist:"
    echo "$REMAINING"
fi

echo ""
echo "Ready for fresh build!"
