#!/bin/sh

echo "========================================="
echo " Notifinho v1.0.0"
echo " Infrastructure Notification Engine"
echo "========================================="

mkdir -p /notifinho/logs/emails
touch /notifinho/logs/notifinho.log

cd /notifinho/src

echo
echo "[1/1] Starting Notifinho..."

python3 main.py
