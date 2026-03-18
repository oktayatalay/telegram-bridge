#!/bin/bash

# Claude Code Stop hook — görev tamamlandığında son yanıtı Telegram'a gönderir

BRIDGE_DIR="$HOME/telegram-bridge"
source "$BRIDGE_DIR/config.env"

# TMUX socket'i bul (hook subprocess'ine TMUX env geçmez)
if [ -z "$TMUX" ]; then
    TMUX_SOCK="/tmp/tmux-$(id -u)/default"
    [ -S "$TMUX_SOCK" ] && export TMUX="$TMUX_SOCK,0,0"
fi

SESSION=$(tmux display-message -p '#S' 2>/dev/null || echo "bilinmiyor")

# stdin'i temp dosyaya yaz
HOOK_TMP=$(mktemp /tmp/notify_hook_XXXXXX.json)
cat > "$HOOK_TMP"
# Debug: hook girdisini logla
cp "$HOOK_TMP" /tmp/notify_last_hook.json

python3 - "$BRIDGE_DIR" "$SESSION" "$HOOK_TMP" << 'PYEOF'
import json, sys, os, urllib.request

bridge_dir = sys.argv[1]
session = sys.argv[2]
hook_tmp = sys.argv[3]

with open(f"{bridge_dir}/config.env") as f:
    config = {}
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            config[k.strip()] = v.strip()

token = config["TELEGRAM_TOKEN"]
chat_id = config["CHAT_ID"]

try:
    with open(hook_tmp) as f:
        data = json.load(f)
    last_text = data.get("last_assistant_message", "").strip()
except Exception:
    last_text = ""
finally:
    os.unlink(hook_tmp)

if last_text:
    text = f"<b>[{session}]</b>\n{last_text}"[:4096]
else:
    text = f"✅ [{session}] tamamladı."

payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
req = urllib.request.Request(
    f"https://api.telegram.org/bot{token}/sendMessage",
    data=payload,
    headers={"Content-Type": "application/json"}
)
try:
    urllib.request.urlopen(req, timeout=10)
except Exception as e:
    sys.stderr.write(f"[notify] hata: {e}\n")
PYEOF

exit 0
