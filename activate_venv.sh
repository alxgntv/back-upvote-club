#!/bin/bash
# Скрипт для автоматической активации виртуального окружения в папке backend

# Проверяем, что мы находимся в папке backend
if [[ "$(basename "$PWD")" != "backend" ]]; then
    echo "❌ Этот скрипт должен запускаться из папки backend"
    exit 1
fi

# Проверяем существование виртуального окружения
if [[ ! -f "../venv/bin/activate" ]]; then
    echo "❌ Виртуальное окружение не найдено в ../venv/"
    echo "💡 Создайте виртуальное окружение командой: python -m venv ../venv"
    exit 1
fi

# Активируем виртуальное окружение
source ../venv/bin/activate

# Устанавливаем переменные окружения для Django
export DJANGO_SETTINGS_MODULE=buddyboost.settings
export PYTHONPATH="${PWD}:${PYTHONPATH}"

# Выводим информацию о активированном окружении
echo "✅ Virtual environment activated successfully!"
echo "🐍 Python path: $(which python)"
echo "📁 Working directory: $(pwd)"
echo "🔧 Django settings: $DJANGO_SETTINGS_MODULE"
echo "📦 Installed packages: $(pip list | wc -l) packages"
