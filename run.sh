#!/bin/bash
echo ""
echo "  ▶ YouTube Upload - تطبيق إدارة قناة يوتيوب"
echo "  ═══════════════════════════════════════════"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "  ❌ Python3 غير مثبت!"
    exit 1
fi

# Install dependencies
echo "  📦 جاري فحص المتطلبات..."
pip3 install -r requirements.txt --quiet 2>/dev/null

# Run
echo "  🚀 جاري تشغيل التطبيق..."
echo ""
python3 main.py
