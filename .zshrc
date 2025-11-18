# Автоматическая активация виртуального окружения для папки backend
# Этот файл будет загружен при входе в папку backend

# Функция для проверки и активации виртуального окружения
activate_backend_venv() {
    # Проверяем, что мы находимся в папке backend
    if [[ "$(basename "$PWD")" == "backend" ]]; then
        # Проверяем, не активировано ли уже виртуальное окружение
        if [[ -z "$VIRTUAL_ENV" ]]; then
            # Проверяем существование виртуального окружения
            if [[ -f "../venv/bin/activate" ]]; then
                echo "🐍 Activating virtual environment for backend..."
                source ../venv/bin/activate
                
                # Устанавливаем переменные окружения для Django
                export DJANGO_SETTINGS_MODULE=buddyboost.settings
                export PYTHONPATH="${PWD}:${PYTHONPATH}"
                
                echo "✅ Backend virtual environment activated!"
                echo "📁 Working directory: $(pwd)"
                echo "🔧 Django settings: $DJANGO_SETTINGS_MODULE"
            else
                echo "❌ Virtual environment not found at ../venv/"
                echo "💡 Create it with: python -m venv ../venv"
            fi
        fi
    fi
}

# Автоматически вызываем функцию при загрузке
activate_backend_venv

# Добавляем алиас для быстрой активации
alias activate_venv="source activate_venv.sh"
alias deactivate_venv="deactivate"

# Показываем доступные команды
echo "🚀 Backend environment ready!"
echo "📋 Available commands:"
echo "   activate_venv  - Manually activate virtual environment"
echo "   deactivate_venv - Deactivate virtual environment"
echo "   python manage.py - Django management commands"
