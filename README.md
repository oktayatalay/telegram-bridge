# Telegram Claude Bridge

Control and monitor your [Claude Code](https://claude.ai/code) sessions remotely via Telegram.

## ⚠️ Known Issues & Limitations

These are confirmed issues. Contributions welcome.

### 1. tmux popup doesn't work while Claude Code is active
**Status:** Not fixed
When Claude Code is running interactively, its TUI takes over terminal input. The tmux `display-popup` either doesn't render visibly or can't receive keystrokes. In practice, **Telegram is the only reliable approval channel** while Claude Code is running. The popup only works if you run `claude` inside a tmux session and Claude Code is idle/waiting.

### 2. Popup closes instantly if Telegram approval arrives first
**Status:** By design, but jarring
Both channels race. If you approve on Telegram before the popup even renders, the popup script detects the response file and exits immediately — you never see it. No fix planned; this is the intended race behavior.

### 3. Only one CHAT_ID supported
**Status:** Not fixed
The bot only responds to a single Telegram user (configured in `config.env`). There's no multi-user or team approval flow. All approvals come from one account.

### 4. No persistence across bot restarts for pending approvals
**Status:** Partial workaround
If `bot_poller.py` crashes while a hook is waiting, the hook will block until the 1-hour timeout. Restarting the bot alone doesn't re-send pending requests — you need to run `python3 resend_pending.py` manually.

### 5. 1-hour approval timeout may be too long
**Status:** Not fixed
If you walk away and forget about a pending approval, Claude Code is blocked for up to 1 hour before it auto-denies. The timeout is hardcoded in `hook.sh`. Easy to change but not configurable yet.

### 6. systemd user service requires lingering to survive logout
**Status:** Known caveat
On systems where you log out (not just close the terminal), the user service stops. Fix:
```bash
loginctl enable-linger $USER
```

---

## What it does

- **Approval gate**: Every `Bash`, `Edit`, `Write` tool call Claude makes sends a Telegram message with **Approve / Deny** inline buttons. You can also approve from the terminal popup — whichever comes first wins.
- **Completion notifications**: When Claude finishes a task, its final response is sent to Telegram.
- **Notification forwarding**: Claude's `Notification` events (mid-task messages) are forwarded to Telegram.
- **Session management**: Create and switch between tmux sessions from Telegram. Send text to the active session directly.
- **Image forwarding**: Send a photo from Telegram — it gets downloaded to `/tmp` and the path is forwarded to the active Claude session.

## Architecture

```
Claude Code → hook.sh ──► pending/<ID>.json + Telegram message (inline buttons)
                    │                              │
                    ▼                              ▼
            tmux popup (y/n)           bot_poller.py (long-poll)
                    │                              │
                    └──────── first wins ──────────┘
                                    │
                            responses/<ID>.txt
                                    │
                    hook.sh reads → exit 0 (allow) or exit 2 (deny)
```

**File-based IPC** (no database, no Redis):
- `pending/<ID>.json` — created by `hook.sh` when approval is needed
- `responses/<ID>.txt` — written by bot poller or terminal popup
- `active_session.txt` — currently active tmux session name

## Requirements

- Linux with tmux
- Python 3 (stdlib only — no pip install needed)
- `inotifywait` (`inotify-tools` package) — used by `hook.sh` for zero-latency response detection
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))

```bash
# Ubuntu/Debian
sudo apt install tmux inotify-tools

# Arch
sudo pacman -S tmux inotify-tools
```

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/telegram-bridge.git ~/telegram-bridge
cd ~/telegram-bridge
mkdir -p pending responses
```

### 2. Create your Telegram bot

1. Open Telegram → search **@BotFather** → `/newbot`
2. Choose a name and username (must end in `_bot`)
3. Copy the token BotFather gives you

### 3. Get your Chat ID

Send any message to your new bot, then run:

```bash
source config.env  # after filling in TELEGRAM_TOKEN below
curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getUpdates" | python3 -m json.tool | grep '"id"' | head -5
```

The first `"id"` value is your chat ID.

### 4. Configure credentials

```bash
cp config.env.example config.env
# Edit config.env and fill in your TELEGRAM_TOKEN and CHAT_ID
```

`config.env` format:
```
TELEGRAM_TOKEN=123456789:AABBCCDDEEFFaabbccddeeff-xxxxxxxxxx
CHAT_ID=123456789
```

> **Note:** This file is in `.gitignore` — never commit it.

### 5. Start the bot poller

```bash
# Foreground (to test)
python3 bot_poller.py

# Background
python3 bot_poller.py >> bot.log 2>&1 &
```

**Or as a systemd user service (auto-start on login):**

```bash
mkdir -p ~/.config/systemd/user
cp telegram-bridge.service.example ~/.config/systemd/user/telegram-bridge.service

systemctl --user daemon-reload
systemctl --user enable telegram-bridge
systemctl --user start telegram-bridge

# Check status
systemctl --user status telegram-bridge
journalctl --user -u telegram-bridge -f
```

### 6. Add Claude Code hooks

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "bash ~/telegram-bridge/hook.sh" }]
      }
    ],
    "Stop": [
      {
        "hooks": [{ "type": "command", "command": "bash ~/telegram-bridge/notify.sh" }]
      }
    ],
    "Notification": [
      {
        "hooks": [{ "type": "command", "command": "bash ~/telegram-bridge/telegram_notify.sh" }]
      }
    ]
  }
}
```

> The hook only intercepts `Bash` tool calls. Read-only tools (`Read`, `Glob`, `Grep`, `WebFetch`, etc.) pass through silently.

## Telegram commands

| Command | Description |
|---------|-------------|
| `/status` | List tmux sessions (active one marked with ▶) |
| `/new <name>` | Create a new tmux session and start `claude` in it |
| `/switch` | Pick active session via inline buttons |
| `/switch <name>` | Switch directly to named session |
| `/help` | Show command list |
| _free text_ | Sent to the active tmux session as keystrokes |
| _photo_ | Downloaded to `/tmp`, path forwarded to active session |

## File structure

```
telegram-bridge/
├── hook.sh                  # PreToolUse hook — approval gate
├── notify.sh                # Stop hook — completion notification
├── telegram_notify.sh       # Notification hook — mid-task messages
├── bot_poller.py            # Telegram long-poll listener
├── resend_pending.py        # Resend stuck pending approvals (use after bot crash)
├── config.env               # Your credentials (NOT in git)
├── config.env.example       # Template
├── telegram-bridge.service.example  # systemd unit template
├── test_bot.py              # Unit tests
├── pending/                 # Pending approval requests (auto-created)
└── responses/               # Approval responses (auto-created)
```

## Adapting with Claude Code

Once you have cloned the repo, you can ask Claude Code to adapt it for your setup:

```
I've cloned telegram-bridge into ~/telegram-bridge.
Help me set it up — I'm on [Ubuntu/Arch/macOS], using [zsh/bash],
and my tmux socket is at [default/custom path].
```

Claude Code can read the `CLAUDE.md` in this repo and understand the full architecture. You can also ask it to extend the bot (e.g., add new commands, change which tools require approval, add a whitelist).

## Security

- The bot only responds to the exact `CHAT_ID` in `config.env`. All other senders are silently ignored.
- `config.env` is `.gitignore`d — never commit real credentials.
- Approval timeout is 1 hour — after that, the pending action is automatically denied and you get a Telegram notification.

## Troubleshooting

### Hook breaks itself (self-lock)

**Symptom:** All Claude Code tool calls are blocked. Every `Edit`, `Write`, or `Bash` attempt shows a hook error.

**Cause:** `hook.sh` has a syntax error. When bash can't parse it, it exits with code 2, which Claude Code interprets as "deny" — blocking everything including further edits to fix it.

**Why this is unlikely now:** `hook.sh` automatically passes through any edits targeting files inside `~/telegram-bridge/`. So editing the bridge scripts themselves never goes through the hook.

**If it still happens:**

```bash
# 1. Check if hook.sh has a syntax error
bash -n ~/telegram-bridge/hook.sh

# 2a. Restore from git (loses uncommitted changes)
cd ~/telegram-bridge && git checkout hook.sh

# 2b. Or fix the specific line from terminal (bypass Claude Code)
python3 - << 'EOF'
with open('/home/oktay/telegram-bridge/hook.sh') as f:
    content = f.read()
# inspect content, find the broken line, fix it
print(content[content.find('# Telegram'):content.find('# Telegram')+200])
EOF
```

### Bot poller not responding

```bash
systemctl --user status telegram-bridge
systemctl --user restart telegram-bridge
tail -f ~/telegram-bridge/bot.log
```

### Stuck pending approvals (after bot crash)

```bash
python3 ~/telegram-bridge/resend_pending.py
```

## Tests

```bash
python3 -m pytest test_bot.py -v
```

## License

MIT
