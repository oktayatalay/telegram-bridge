# Telegram Claude Bridge — Kurulum Talimatı

Telegram bot token ve chat ID'sini almak için aşağıdaki adımları takip et.

## Step 1: @BotFather'da Bot Oluştur

1. Telegram'ı aç
2. **@BotFather** bul ve sohbet başlat
3. `/newbot` komutunu gönder
4. Bot adı sor → Örneğin: **Claude Bridge**
5. Bot kullanıcı adı sor → **\_bot** ile bitmeli (örn: `claude_bridge_bot`)
6. @BotFather token'ı verecek — **kopyala**

## Step 2: Token'ı Dosyaya Kaydet

1. `~/telegram-bridge/config.env` dosyasını aç
2. `TELEGRAM_TOKEN=` kısmından sonra token'ı yapıştır
3. Dosyayı kaydet

## Step 3: Chat ID'sini Bul

1. Yeni oluşturduğun bota Telegram'da bir mesaj gönder (örn: `/start`)
2. Terminal'de şu komutu çalıştır:

```bash
cd ~/telegram-bridge
source config.env
curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getUpdates" | python3 -m json.tool | grep '"id"' | head -5
```

3. Çıktıda görünen **ilk `"id"` değerini** kopyala (botun gönderdiği mesaj ID'si değil, chat ID'si olacak)
4. `config.env` dosyasında `CHAT_ID=` kısmından sonra yapıştır

## Step 4: config.env'yi Kaydet ve Tamamla

Dosya şu şekilde görünmeli:

```
TELEGRAM_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
CHAT_ID=123456789
```

Hepsi tamam! Artık Telegram bridge kullanmaya başlayabilirsin.
