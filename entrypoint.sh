#!/bin/sh
# Wait for the server to be available
sleep 2
# Run the client
exec python client.py --server=host.docker.internal:8888