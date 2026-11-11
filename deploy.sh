#!/usr/bin/env bash
# ========================================================
# Sozla AI — Linux / Ubuntu VPS 24/7 Avtomatik O'rnatish
# ========================================================

set -e

echo "🚀 Tizim paketlari yangilanmoqda..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git

PROJECT_DIR="/home/ubuntu/Yodla"
if [ ! -d "$PROJECT_DIR" ]; then
    echo "📥 GitHub dan loyiha klonlanmoqda..."
    git clone https://github.com/durd1ma7ov06/Yodla.git "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"

echo "📦 Virtual muhit (venv) yaratilmoqda..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

echo "📦 Kutubxonalar o'rnatilmoqda..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# .env tekshirish
if [ ! -f ".env" ]; then
    echo "⚠️ Diqqat: .env faylini yaratish zarur! .env.example dan nusxa olinmoqda..."
    cp .env.example .env
    echo "Iltimos, '.env' faylini ochib BOT_TOKEN va API kalitlarni kiriting (nano .env)"
fi

echo "⚙️ Systemd servisi yaratilmoqda..."
SERVICE_FILE="/etc/systemd/system/sozla_bot.service"
sudo bash -c "cat > $SERVICE_FILE" <<EOL
[Unit]
Description=Sozla AI Vocabulary Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOL

echo "🔄 Servis ishga tushirilmoqda..."
sudo systemctl daemon-reload
sudo systemctl enable sozla_bot
sudo systemctl restart sozla_bot

echo "✅ Bot muvaffaqiyatli o'rnatildi va 24/7 fonda ishga tushirildi!"
echo "Holatni tekshirish uchun: sudo systemctl status sozla_bot"
echo "Loglarni ko'rish uchun: sudo journalctl -u sozla_bot -f"
