#!/usr/bin/env python3
"""Bekleyen pending isteklerini inline keyboard ile Telegram'a (yeniden) gönderir."""

import os, json, urllib.request

BRIDGE_DIR = os.path.expanduser("~/telegram-bridge")
PENDING_DIR = os.path.join(BRIDGE_DIR, "pending")

config = {}
with open(os.path.join(BRIDGE_DIR, "config.env")) as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            config[k.strip()] = v.strip()

TOKEN = config["TELEGRAM_TOKEN"]
CHAT_ID = config["CHAT_ID"]
URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

for fname in sorted(os.listdir(PENDING_DIR)):
    if not fname.endswith(".json"):
        continue
    with open(os.path.join(PENDING_DIR, fname)) as f:
        data = json.load(f)

    req_id = data["id"]
    command = data.get("command", "?")[:300]
    session = data.get("session", "?")

    text = f"⏳ Bekleyen Onay\nSession: {session}\nKomut:\n<code>{command}</code>\nID: {req_id}"
    keyboard = json.dumps({
        "inline_keyboard": [[
            {"text": "✅ Onayla", "callback_data": f"allow:{req_id}"},
            {"text": "❌ Reddet", "callback_data": f"deny:{req_id}"}
        ]]
    })
    payload = json.dumps({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": keyboard
    }).encode()
    req = urllib.request.Request(URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        print(f"[SENT] {req_id}")
    except Exception as e:
        print(f"[ERROR] {req_id}: {e}")
