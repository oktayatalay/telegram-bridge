# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Proje Özeti

Telegram üzerinden Claude Code oturumlarını uzaktan yönetmek için bir köprü sistemi. Üç Claude Code hook'u ve bir bot poller içerir:

1. **PreToolUse hook** (`hook.sh`): Her Bash komutunu hem tmux popup'ta hem Telegram'da onay butonu ile sorar. İzin verilmezse `exit 2` ile bloklar; `exit 0` ile geçirir.
2. **Stop hook** (`notify.sh`): Görev tamamlandığında Telegram'a "tamamladı" bildirimi gönderir.
3. **Notification hook** (`telegram_notify.sh`): Claude'un Notification event'indeki `message` alanını Telegram'a iletir.
4. **Bot poller** (`bot_poller.py`): Telegram long-polling ile dinler; allow/deny callback'lerini `responses/` klasörüne yazar; tmux session yönetimi sağlar.

## Komutlar

```bash
# Testleri çalıştır
python3 -m pytest test_bot.py -v

# Tek test çalıştır
python3 -m pytest test_bot.py::TestTmuxSend::test_returns_true_on_success -v

# Bot poller'ı başlat (arka planda)
python3 bot_poller.py >> bot.log 2>&1 &

# Bekleyen onayları yeniden gönder (bot çökmüşse)
python3 resend_pending.py
```

## Mimari

**Dosya tabanlı IPC:**
- `pending/<REQUEST_ID>.json` — hook.sh'ın oluşturduğu bekleyen onay kaydı
- `responses/<REQUEST_ID>.txt` — bot_poller.py'nin yazdığı `allow` veya `deny` cevabı
- `active_session.txt` — şu an aktif tmux session adı
- `config.env` — `TELEGRAM_TOKEN` ve `CHAT_ID` (git'te yok, stdlib ile parse edilir)

**Onay akışı:**
```
Claude Code → hook.sh → pending/*.json + Telegram mesajı (inline buton)
                      ↓                    ↓
             tmux popup (y/n)    bot_poller (Telegram'dan allow/deny)
                      ↓                    ↓
               hangisi önce gelirse → responses/<ID>.txt
                                          ↓
              hook.sh okur → exit 0 (izin) veya exit 2 (blok)
```

Telegram mesajı onaylandıktan/reddedildikten sonra güncellenir (butonlar kaldırılır). Terminal'den onaylansa bile Telegram mesajı güncellenir.

**Bot komutları:** `/status`, `/new <isim>`, `/switch [isim]`, `/help` — tmux session yönetimi için.
**Serbest metin:** Aktif tmux session'a `send-keys` ile iletilir.

## Hook Kurulumu (`~/.claude/settings.json`)

```json
{
  "hooks": {
    "PreToolUse": [{ "matcher": "Bash", "hooks": [{ "type": "command", "command": "bash ~/telegram-bridge/hook.sh" }] }],
    "Stop": [{ "hooks": [{ "type": "command", "command": "bash ~/telegram-bridge/notify.sh" }] }],
    "Notification": [{ "hooks": [{ "type": "command", "command": "bash ~/telegram-bridge/telegram_notify.sh" }] }]
  },
  "permissions": { "allow": ["Bash(*)"] }
}
```

`hook.sh` yalnızca `tool_name == "Bash"` olanı yakalar; diğer tool'lar (`Read`, `Edit` vb.) doğrudan geçer.

## config.env Formatı

```
TELEGRAM_TOKEN=123456:ABC-DEF...
CHAT_ID=123456789
```

Tüm script'ler bu dosyayı stdlib ile manuel parse eder (bash `source` veya Python satır satır okuma). Özel karakter içeren değerler tırnak gerektirmez.

## Test Mimarisi

`bot_poller.py` modül seviyesinde `config.env` okuyup `TOKEN`/`CHAT_ID` atadığından doğrudan import edilemiyor. `test_bot.py`, test edilen fonksiyonları parametrik izole kopyalar olarak yeniden tanımlar ve `unittest.mock.patch` ile subprocess çağrılarını mock'lar.
