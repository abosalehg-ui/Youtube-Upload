#!/bin/bash
# تشغيل التطبيق داخل بيئة افتراضية (.venv) — لا يلمس بايثون النظام (PEP 668)
# ولا يخفي أخطاء التثبيت.
set -e
cd "$(dirname "$0")"

echo ""
echo "  ▶ YouTube Upload - تطبيق إدارة قناة يوتيوب"
echo "  ═══════════════════════════════════════════"
echo ""

if ! command -v python3 &> /dev/null; then
    echo "  ❌ Python3 غير مثبت!"
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "  📦 إنشاء بيئة افتراضية (.venv)..."
    python3 -m venv .venv
fi

echo "  📦 جاري فحص المتطلبات..."
.venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt

echo "  🚀 جاري تشغيل التطبيق..."
echo ""
exec .venv/bin/python main.py
