#!/bin/sh

APP_VERSION=$(python3 - <<'PY'
import sys
sys.path.insert(0, "/notifinho/src")
from version import VERSION
print(VERSION)
PY
)

echo "========================================="
echo " Notifinho ${APP_VERSION}"
echo " Infrastructure Notification Engine"
echo "========================================="

mkdir -p /notifinho/logs/emails
touch /notifinho/logs/notifinho.log

cd /notifinho/src

echo
echo "[1/1] Starting Notifinho..."

python3 main.py
