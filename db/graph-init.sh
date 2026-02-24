#!/bin/sh
# FalkorDB startup script — starts Redis, then creates the empty 'pkg' graph.
# Mounted as the container entrypoint in docker-compose.yml.
set -e

# Start Redis/FalkorDB in the background
redis-server --loadmodule /usr/lib/redis/modules/libgraph.so &
REDIS_PID=$!

# Wait for Redis to be ready
until redis-cli -p 6379 PING 2>/dev/null | grep -q PONG; do
  sleep 0.5
done

# Create the 'pkg' graph if it doesn't exist
# GRAPH.QUERY on a non-existent graph creates it implicitly in FalkorDB
redis-cli -p 6379 GRAPH.QUERY pkg "MATCH (n) RETURN count(n)" > /dev/null 2>&1 || true

echo "pkg graph initialised"

# Hand off to the Redis process
wait $REDIS_PID
