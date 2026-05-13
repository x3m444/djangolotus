#!/bin/bash
set -e

cd ~/djangolotus
git pull
docker compose up --build -d
echo "Deploy finalizat."
