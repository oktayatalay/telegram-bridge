#!/bin/bash

# Claude Code PreToolUse hook
# stdin'den JSON alır, write/execute tool'larını Telegram'a onay için gönderir
# exit 0 = izin ver, exit 2 = reddet

BRIDGE_DIR="$HOME/telegram-bridge"
source "$BRIDGE_DIR/config.env"

# TMUX socket'i bul (Claude Code hook subprocess'ine TMUX env geçmez)
TMUX_SOCK="/tmp/tmux-$(id -u)/default"
if [ -n "$TMUX" ]; then
    TMUX_CMD="tmux"
elif [ -S "$TMUX_SOCK" ]; then
    TMUX_CMD="tmux -S $TMUX_SOCK"
else
    TMUX_CMD=""
fi

HOOK_DATA=$(cat)

# Tool adını ve gösterim metnini çıkar
# Read-only tool'lar için PASSTHROUGH döner → direkt exit 0
TOOL_INFO=$(HOOK_JSON="$HOOK_DATA" python3 2>/dev/null << 'PYEOF'
import json, os

d = json.loads(os.environ["HOOK_JSON"])
tool = d.get("tool_name", "")
inp = d.get("tool_input", {})

# Bridge dizinindeki dosyaları düzenlerken onay isteme (self-lock koruması)
BRIDGE_DIR = os.path.expanduser("~/telegram-bridge")
if tool in ("Edit", "Write", "MultiEdit"):
    fp = inp.get("file_path", "")
    if fp.startswith(BRIDGE_DIR):
        print("PASSTHROUGH")
        sys.exit(0)

PASSTHROUGH = {
    "Read", "Glob", "Grep", "LS",
    "WebFetch", "WebSearch",
    "AskUserQuestion", "ToolSearch", "Skill",
    "TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "TaskOutput", "TaskStop",
    "Agent", "EnterPlanMode", "ExitPlanMode", "EnterWorktree", "ExitWorktree",
    "CronList", "SendMessage",
}

if tool in PASSTHROUGH:
    print("PASSTHROUGH")
    sys.exit(0)

if tool == "Bash":
    info = inp.get("command", "?")
elif tool == "Edit":
    fp = inp.get("file_path", "?")
    old = (inp.get("old_string", "") or "")[:80].replace("\n", "↵")
    new = (inp.get("new_string", "") or "")[:80].replace("\n", "↵")
    info = f"📝 {fp}\n- {old}\n+ {new}" if old else f"📝 {fp}"
elif tool == "MultiEdit":
    fp = inp.get("file_path", "?")
    count = len(inp.get("edits", []))
    info = f"📝 {fp} ({count} düzenleme)"
elif tool == "Write":
    fp = inp.get("file_path", "?")
    size = len(inp.get("content", ""))
    info = f"💾 {fp} ({size} karakter)"
elif tool == "NotebookEdit":
    info = f"📓 {inp.get('notebook_path', '?')}"
elif tool in ("CronCreate", "CronDelete"):
    info = json.dumps(inp)[:200]
else:
    info = json.dumps(inp)[:300]

# İlk satır: tool adı, geri kalan: detay
print(f"[{tool}] {info}")
PYEOF
)

TOOL_NAME=$(echo "$HOOK_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null)

# Read-only → geç
if [ "$TOOL_INFO" = "PASSTHROUGH" ] || [ -z "$TOOL_INFO" ]; then
    exit 0
fi

# Aktif session'ı bul — önce TMUX env'den, yoksa socket üzerinden en son aktif session
if [ -n "$TMUX" ]; then
    SESSION=$(tmux display-message -p '#S' 2>/dev/null || echo "bilinmiyor")
elif [ -n "$TMUX_CMD" ]; then
    SESSION=$($TMUX_CMD list-sessions -F '#{session_last_attached} #{session_name}' 2>/dev/null \
        | sort -rn | head -1 | awk '{print $2}')
    [ -z "$SESSION" ] && SESSION="bilinmiyor"
else
    SESSION="bilinmiyor"
fi
REQUEST_ID=$(date +%s%N)
export REQUEST_ID

PENDING_FILE="$BRIDGE_DIR/pending/${REQUEST_ID}.json"
RESPONSE_FILE="$BRIDGE_DIR/responses/${REQUEST_ID}.txt"

# Pending JSON yaz
python3 -c "
import json, sys, os
data = {
    'id': os.environ['REQUEST_ID'],
    'session': sys.argv[1],
    'command': sys.argv[2],
    'timestamp': sys.argv[3],
    'message_id': ''
}
print(json.dumps(data, indent=2))
" "$SESSION" "$TOOL_INFO" "$(date -Iseconds)" > "$PENDING_FILE"

# Telegram'a gönder ve message_id al (3 deneme)
MSG_ID=$(python3 - 2>>"$BRIDGE_DIR/hook.log" << 'PYEOF'
import os, urllib.request, json, time, sys

bridge_dir = os.path.expanduser("~/telegram-bridge")
with open(f"{bridge_dir}/config.env") as f:
    config = {}
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            config[k.strip()] = v.strip()

req_id = os.environ["REQUEST_ID"]
with open(f"{bridge_dir}/pending/{req_id}.json") as f:
    data = json.load(f)

raw = data["command"]
session = data["session"]
token = config["TELEGRAM_TOKEN"]
chat_id = config["CHAT_ID"]

# Araç tipini ve detayı ayır: "[Bash] komut" → tip=Bash, detay=komut
if raw.startswith("[") and "]" in raw:
    bracket_end = raw.index("]")
    tool_type = raw[1:bracket_end]
    detail = raw[bracket_end+2:]  # "] " sonrası
else:
    tool_type = "?"
    detail = raw

import html as html_mod
lines = detail.split("\n")
detail_text = html_mod.escape("\n".join(lines[:20])[:800])

text = (
    f"⚠️ <b>Onay Gerekiyor</b>\n"
    f"━━━━━━━━━━━━━━━━━━━\n"
    f"Session : <code>{html_mod.escape(session)}</code>\n"
    f"Araç    : <b>{html_mod.escape(tool_type)}</b>\n"
    f"━━━━━━━━━━━━━━━━━━━\n"
    f"<pre>{detail_text}</pre>"
)
keyboard = json.dumps({
    "inline_keyboard": [[
        {"text": "✅ Onayla", "callback_data": f"allow:{req_id}"},
        {"text": "❌ Reddet", "callback_data": f"deny:{req_id}"}
    ]]
})
url = f"https://api.telegram.org/bot{token}/sendMessage"
payload = json.dumps({
    "chat_id": chat_id,
    "text": text,
    "parse_mode": "HTML",
    "reply_markup": keyboard
}).encode()

for attempt in range(3):
    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        msg_id = result.get("result", {}).get("message_id", "")
        if msg_id:
            print(msg_id)
            sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"[hook] Telegram send attempt {attempt+1} failed: {e}\n")
        if attempt < 2:
            time.sleep(1)

print("")
PYEOF
)

# Pending JSON'a message_id ekle
if [ -n "$MSG_ID" ]; then
    python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
data['message_id'] = sys.argv[2]
with open(sys.argv[1], 'w') as f:
    json.dump(data, f, indent=2)
" "$PENDING_FILE" "$MSG_ID"
fi

# tmux popup için formatla
# TOOL_INFO: "[Bash] komut" veya "[Edit] 📝 dosya\n- eski\n+ yeni"
POPUP_TOOL="$TOOL_NAME"
POPUP_DETAIL=$(echo "$TOOL_INFO" | sed "s/^\[$TOOL_NAME\] //")
# Satır başına 2 boşluk ekle, maksimum 15 satır
POPUP_BODY=$(echo "$POPUP_DETAIL" | head -15 | fold -w 76 -s | sed 's/^/  /')

POPUP_SCRIPT=$(mktemp /tmp/tg_hook_XXXXXX.sh)
RF="$RESPONSE_FILE"
cat > "$POPUP_SCRIPT" << POPUPEOF
#!/bin/bash
# Ekranı bir kez çiz, döngüde temizleme
clear
echo "============================================================"
echo "  ONAY GEREKIYOR"
echo "============================================================"
echo "  Session : $SESSION"
echo "  Arac    : $POPUP_TOOL"
echo "------------------------------------------------------------"
echo ""
echo "$POPUP_BODY"
echo ""
echo "------------------------------------------------------------"
echo "  [Enter] Onayla    [Esc / n] Reddet"
echo "============================================================"

# Kullanıcı girişi veya Telegram cevabını bekle
while [ ! -f "$RF" ]; do
    read -s -t 1 -n1 ans
    RC=\$?
    if [ \$RC -eq 0 ]; then
        if [ -z "\$ans" ]; then
            # Enter
            echo "allow" > "$RF"
        elif [ "\$ans" = $'\033' ] || [ "\$ans" = "n" ] || [ "\$ans" = "N" ]; then
            # Esc veya n
            read -s -t 0.1 -n10 2>/dev/null  # kalan escape seq'i tüket
            echo "deny" > "$RF"
        fi
    fi
done

SONUC=\$(cat "$RF")
echo ""
if [ "\$SONUC" = "allow" ]; then
    echo "  Onaylandi."
else
    echo "  Reddedildi."
fi
sleep 1
POPUPEOF
chmod +x "$POPUP_SCRIPT"

# Popup'u aç (arka planda) — session'ı explicit hedef al
if [ -n "$TMUX_CMD" ] && [ "$SESSION" != "bilinmiyor" ]; then
    $TMUX_CMD display-popup -t "$SESSION" -w 90% -h 22 -E "bash $POPUP_SCRIPT" 2>/dev/null &
elif [ -n "$TMUX_CMD" ]; then
    $TMUX_CMD display-popup -w 90% -h 22 -E "bash $POPUP_SCRIPT" 2>/dev/null &
fi

# Hangisi önce gelirse (popup veya Telegram) onu kullan
# inotifywait ile kernel event'i bekle — polling yok, 1 saat timeout
DEADLINE=$(($(date +%s) + 3600))
while [ ! -f "$RESPONSE_FILE" ]; do
    REMAINING=$((DEADLINE - $(date +%s)))
    if [ $REMAINING -le 0 ]; then
        echo "deny" > "$RESPONSE_FILE"
        echo "[hook] WARN: 1h timeout, reddedildi: $TOOL_INFO" >> "$BRIDGE_DIR/hook.log"
        python3 - "$BRIDGE_DIR" "$SESSION" "$TOOL_INFO" 2>>"$BRIDGE_DIR/hook.log" << 'TIMEOUT_PYEOF'
import sys, json, urllib.request
bridge_dir, session, info = sys.argv[1], sys.argv[2], sys.argv[3]
with open(f"{bridge_dir}/config.env") as f:
    config = {}
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            config[k.strip()] = v.strip()
text = f"⏰ <b>[{session}] 1 saat cevap gelmedi — reddedildi!</b>\n<code>{info[:300]}</code>"
payload = json.dumps({"chat_id": config["CHAT_ID"], "text": text, "parse_mode": "HTML"}).encode()
req = urllib.request.Request(
    f"https://api.telegram.org/bot{config['TELEGRAM_TOKEN']}/sendMessage",
    data=payload, headers={"Content-Type": "application/json"}
)
try:
    urllib.request.urlopen(req, timeout=10)
except Exception as e:
    sys.stderr.write(f"[hook] timeout notify failed: {e}\n")
TIMEOUT_PYEOF
        break
    fi
    inotifywait -e create "$BRIDGE_DIR/responses/" -t "$REMAINING" --quiet 2>/dev/null
done

# Popup'u kapat ve temizle
[ -n "$TMUX_CMD" ] && $TMUX_CMD display-popup -C 2>/dev/null
rm -f "$POPUP_SCRIPT"

RESPONSE=$(cat "$RESPONSE_FILE")
rm -f "$RESPONSE_FILE"
rm -f "$PENDING_FILE"
rm -f "$BRIDGE_DIR/pending/${REQUEST_ID}.sent"

# Telegram mesajını güncelle
if [ -n "$MSG_ID" ]; then
    python3 -c "
import sys, json, urllib.request
bridge_dir = sys.argv[1]
msg_id = sys.argv[2]
response = sys.argv[3]

with open(f'{bridge_dir}/config.env') as f:
    config = {}
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            config[k.strip()] = v.strip()

token = config['TELEGRAM_TOKEN']
chat_id = config['CHAT_ID']
emoji = '✅' if response == 'allow' else '❌'
status = 'Onaylandı' if response == 'allow' else 'Reddedildi'
tool_info = sys.argv[4] if len(sys.argv) > 4 else ''

import html as html_mod
detail = ''
if tool_info:
    raw = tool_info
    if raw.startswith('[') and ']' in raw:
        bracket_end = raw.index(']')
        tool_type = raw[1:bracket_end]
        det = raw[bracket_end+2:]
    else:
        tool_type, det = '?', raw
    lines = det.split('\n')
    detail = '\n<b>' + html_mod.escape(tool_type) + '</b>\n<pre>' + html_mod.escape('\n'.join(det_lines[:10])[:400]) + '</pre>'

payload = json.dumps({
    'chat_id': chat_id,
    'message_id': int(msg_id),
    'text': f'{emoji} <b>{status}</b>{detail}',
    'parse_mode': 'HTML'
}).encode()
req = urllib.request.Request(
    f'https://api.telegram.org/bot{token}/editMessageText',
    data=payload, headers={'Content-Type': 'application/json'}
)
try:
    urllib.request.urlopen(req, timeout=10)
except Exception:
    pass
" "$BRIDGE_DIR" "$MSG_ID" "$RESPONSE" 2>/dev/null
fi

if [ "$RESPONSE" = "allow" ]; then
    exit 0
else
    exit 2
fi
