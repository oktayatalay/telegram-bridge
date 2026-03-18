#!/usr/bin/env python3
"""
Telegram bot poller — callback_query ve message olaylarını dinler.
- allow/deny callback'lerini responses/ klasörüne yazar
- /status, /new, /switch, /help komutlarını işler
- Serbest metin → aktif tmux session'a gönderir
"""

import os
import json
import urllib.request
import urllib.parse
import subprocess
import time

BRIDGE_DIR = os.path.expanduser("~/telegram-bridge")
RESPONSES_DIR = os.path.join(BRIDGE_DIR, "responses")
ACTIVE_SESSION_FILE = os.path.join(BRIDGE_DIR, "active_session.txt")
os.makedirs(RESPONSES_DIR, exist_ok=True)

# config.env oku
config = {}
with open(os.path.join(BRIDGE_DIR, "config.env")) as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            config[k.strip()] = v.strip()

TOKEN = config["TELEGRAM_TOKEN"]
CHAT_ID = str(config["CHAT_ID"])
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"


# ─── Telegram API yardımcıları ───────────────────────────────────────────────

def api_call(method, payload=None):
    url = f"{BASE_URL}/{method}"
    if payload:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[ERROR] {method}: {e}")
        return None


def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return api_call("sendMessage", payload)


def answer_callback(callback_id, text=""):
    api_call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})


def edit_message_text(chat_id, message_id, text):
    api_call("editMessageText", {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML"
    })


# ─── Aktif session yönetimi ──────────────────────────────────────────────────

def get_active_session():
    if os.path.exists(ACTIVE_SESSION_FILE):
        with open(ACTIVE_SESSION_FILE) as f:
            return f.read().strip()
    return None


def set_active_session(name):
    with open(ACTIVE_SESSION_FILE, "w") as f:
        f.write(name)


# ─── tmux yardımcıları ───────────────────────────────────────────────────────

def tmux_list_sessions():
    """Mevcut tmux session listesini döner. tmux yoksa [] döner."""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return []
        sessions = [s.strip() for s in result.stdout.strip().splitlines() if s.strip()]
        return sessions
    except FileNotFoundError:
        return None  # tmux kurulu değil
    except Exception as e:
        print(f"[WARN] tmux list-sessions: {e}")
        return []


def tmux_new_session(name):
    """Yeni tmux session başlatır, içine claude gönderir."""
    try:
        result = subprocess.run(
            ["tmux", "new-session", "-d", "-s", name],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return False, result.stderr.strip()
        # claude komutunu gönder
        subprocess.run(
            ["tmux", "send-keys", "-t", name, "claude", "Enter"],
            capture_output=True, timeout=5
        )
        return True, None
    except FileNotFoundError:
        return False, "tmux kurulu değil"
    except Exception as e:
        return False, str(e)


def tmux_send(session, text):
    """Aktif session'a metin gönderir."""
    try:
        result = subprocess.run(
            ["tmux", "send-keys", "-t", session, text, "Enter"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False
    except Exception as e:
        print(f"[WARN] tmux send-keys: {e}")
        return False


def session_exists(name):
    sessions = tmux_list_sessions()
    if sessions is None:
        return False
    return name in sessions


# ─── Komut işleyicileri ──────────────────────────────────────────────────────

def handle_status(chat_id):
    sessions = tmux_list_sessions()
    if sessions is None:
        send_message(chat_id, "tmux kurulu degil.")
        return
    if not sessions:
        send_message(chat_id, "Hic aktif tmux session yok.")
        return
    active = get_active_session()
    lines = []
    for s in sessions:
        marker = " ▶" if s == active else ""
        lines.append(f"<code>{s}</code>{marker}")
    send_message(chat_id, "Tmux sessionlar:\n" + "\n".join(lines))


def handle_new(chat_id, name):
    if not name:
        send_message(chat_id, "Kullanim: /new <session-adi>")
        return
    sessions = tmux_list_sessions()
    if sessions is None:
        send_message(chat_id, "tmux kurulu degil.")
        return
    if name in sessions:
        send_message(chat_id, f"'{name}' session zaten mevcut. /switch {name} ile gecebilirsin.")
        return
    ok, err = tmux_new_session(name)
    if ok:
        set_active_session(name)
        send_message(chat_id, f"Session '<code>{name}</code>' olusturuldu ve aktif yapildi. claude baslatildi.")
    else:
        send_message(chat_id, f"Session olusturulamadi: {err}")


def handle_switch_inline(chat_id):
    sessions = tmux_list_sessions()
    if sessions is None:
        send_message(chat_id, "tmux kurulu degil.")
        return
    if not sessions:
        send_message(chat_id, "Hic aktif tmux session yok.")
        return
    active = get_active_session()
    buttons = []
    for s in sessions:
        label = f"▶ {s}" if s == active else s
        buttons.append([{"text": label, "callback_data": f"switch:{s}"}])
    reply_markup = {"inline_keyboard": buttons}
    send_message(chat_id, "Session sec:", reply_markup=reply_markup)


def handle_switch_direct(chat_id, name):
    if not session_exists(name):
        sessions = tmux_list_sessions()
        if sessions is None:
            send_message(chat_id, "tmux kurulu degil.")
        else:
            send_message(chat_id, f"'{name}' session bulunamadi. Mevcut sessionlar: {', '.join(sessions) or 'yok'}")
        return
    set_active_session(name)
    send_message(chat_id, f"Aktif session: <code>{name}</code>")


def handle_help(chat_id):
    text = (
        "<b>Komutlar:</b>\n"
        "/status — tmux session listesi\n"
        "/new &lt;isim&gt; — yeni session + claude\n"
        "/switch — session sec (butonlarla)\n"
        "/switch &lt;isim&gt; — dogrudan gecis\n"
        "/help — bu mesaj\n\n"
        "<b>Serbest metin</b> → aktif session'a gonderilir"
    )
    send_message(chat_id, text)


def handle_free_text(chat_id, text):
    active = get_active_session()
    if not active:
        send_message(chat_id, "Aktif session yok. Once /new veya /switch kullan.")
        return
    if not session_exists(active):
        send_message(chat_id, f"'{active}' session artik mevcut degil. /status ile kontrol et.")
        return
    ok = tmux_send(active, text)
    if not ok:
        send_message(chat_id, "tmux'a gonderilemedi.")


def handle_photo(chat_id, msg):
    """Telegram'dan gelen görseli indir, /tmp'ye kaydet, tmux'a path'i gönder."""
    active = get_active_session()
    if not active:
        send_message(chat_id, "Aktif session yok. Once /new veya /switch kullan.")
        return
    if not session_exists(active):
        send_message(chat_id, f"'{active}' session artik mevcut degil.")
        return

    # En yüksek çözünürlüklü fotoğrafı al
    photos = msg.get("photo", [])
    if not photos:
        return
    file_id = photos[-1]["file_id"]

    # getFile ile download path al
    result = api_call("getFile", {"file_id": file_id})
    if not result or not result.get("ok"):
        send_message(chat_id, "Gorsel indirilemedi.")
        return

    file_path = result["result"]["file_path"]
    ext = os.path.splitext(file_path)[1] or ".jpg"
    local_path = f"/tmp/tg_image_{file_id[:8]}{ext}"

    url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            with open(local_path, "wb") as f:
                f.write(resp.read())
    except Exception as e:
        send_message(chat_id, f"Gorsel indirme hatasi: {e}")
        return

    # Caption varsa birlikte gönder
    caption = msg.get("caption", "").strip()
    if caption:
        tmux_send(active, caption)

    # Görseli Claude'a okuması için path'i gönder
    tmux_send(active, local_path)
    send_message(chat_id, f"Gorsel gonderildi: <code>{local_path}</code>", reply_markup=None)


# ─── Update işleyicileri ─────────────────────────────────────────────────────

def process_message(msg):
    chat_id = str(msg.get("chat", {}).get("id", ""))
    if chat_id != CHAT_ID:
        print(f"[SKIP] Yetkisiz chat_id: {chat_id}")
        return

    # Görsel mesajı
    if "photo" in msg:
        handle_photo(chat_id, msg)
        return

    text = msg.get("text", "").strip()
    if not text:
        return

    if text == "/status":
        handle_status(chat_id)
    elif text.startswith("/new"):
        parts = text.split(None, 1)
        name = parts[1].strip() if len(parts) > 1 else ""
        handle_new(chat_id, name)
    elif text == "/switch":
        handle_switch_inline(chat_id)
    elif text.startswith("/switch "):
        name = text[len("/switch "):].strip()
        handle_switch_direct(chat_id, name)
    elif text == "/help" or text == "/start":
        handle_help(chat_id)
    elif text.startswith("/"):
        send_message(chat_id, f"Bilinmeyen komut: {text}\n/help ile komutlari gor.")
    else:
        handle_free_text(chat_id, text)


def process_callback_query(cq):
    chat_id = str(cq.get("message", {}).get("chat", {}).get("id", ""))
    if chat_id != CHAT_ID:
        print(f"[SKIP] Yetkisiz callback chat_id: {chat_id}")
        answer_callback(cq["id"])
        return

    callback_id = cq["id"]
    data = cq.get("data", "")
    message_id = cq.get("message", {}).get("message_id")

    if ":" not in data:
        answer_callback(callback_id)
        return

    action, value = data.split(":", 1)

    # allow/deny — mevcut dosya tabanlı mekanizma
    if action in ("allow", "deny"):
        request_id = value
        response_file = os.path.join(RESPONSES_DIR, f"{request_id}.txt")

        # Zaten işlendiyse (terminal'den veya önceki butona basıştan)
        if os.path.exists(response_file):
            answer_callback(callback_id, "Zaten işlendi")
            return

        # Response yaz
        with open(response_file, "w") as f:
            f.write(action)

        emoji = "✅" if action == "allow" else "❌"
        status = "Onaylandı" if action == "allow" else "Reddedildi"

        # Telegram mesajını güncelle (butonları kaldır)
        if message_id:
            edit_message_text(chat_id, message_id, f"{emoji} {status}")

        answer_callback(callback_id, status)
        print(f"[{'OK' if action == 'allow' else 'DENY'}] {request_id} {status}")

    # switch — inline buton session secimi
    elif action == "switch":
        session_name = value
        if not session_exists(session_name):
            answer_callback(callback_id, f"'{session_name}' artik mevcut degil")
            if message_id:
                edit_message_text(chat_id, message_id, f"Session bulunamadi: {session_name}")
        else:
            set_active_session(session_name)
            answer_callback(callback_id, f"Aktif: {session_name}")
            if message_id:
                edit_message_text(chat_id, message_id, f"Aktif session: <code>{session_name}</code>")

    else:
        answer_callback(callback_id)


# ─── Ana dongu ───────────────────────────────────────────────────────────────

def main():
    offset = None
    print("[bot_poller] Baslatildi. Telegram mesajlari dinleniyor...")

    while True:
        params = {
            "timeout": 25,
            "allowed_updates": json.dumps(["callback_query", "message"])
        }
        if offset:
            params["offset"] = offset

        url = f"{BASE_URL}/getUpdates?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=35) as resp:
                result = json.loads(resp.read())
        except Exception as e:
            print(f"[WARN] getUpdates hata: {e}")
            time.sleep(3)
            continue

        if not result.get("ok"):
            time.sleep(3)
            continue

        for update in result.get("result", []):
            offset = update["update_id"] + 1

            if "callback_query" in update:
                process_callback_query(update["callback_query"])
            elif "message" in update:
                process_message(update["message"])


if __name__ == "__main__":
    main()
