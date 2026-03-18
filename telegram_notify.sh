#!/bin/bash

# Claude Code Notification hook — yanıt metnini Telegram'a gönderir

BRIDGE_DIR="$HOME/telegram-bridge"
source "$BRIDGE_DIR/config.env"

HOOK_DATA=$(cat)

MESSAGE=$(echo "$HOOK_DATA" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('message', ''))
except:
    print('')
" 2>/dev/null)

if [ -z "$MESSAGE" ]; then
    exit 0
fi

SESSION=$(tmux display-message -p '#S' 2>/dev/null || echo "")
PREFIX=""
[ -n "$SESSION" ] && PREFIX="[${SESSION}] "

python3 -c "
import urllib.request, json, sys

token = '$TELEGRAM_TOKEN'
chat_id = '$CHAT_ID'
text = sys.argv[1]

payload = json.dumps({
    'chat_id': chat_id,
    'text': text,
    'parse_mode': 'HTML'
}).encode()

req = urllib.request.Request(
    f'https://api.telegram.org/bot{token}/sendMessage',
    data=payload,
    headers={'Content-Type': 'application/json'}
)
try:
    urllib.request.urlopen(req, timeout=10)
except Exception:
    pass
" "${PREFIX}${MESSAGE}" 2>/dev/null

exit 0
