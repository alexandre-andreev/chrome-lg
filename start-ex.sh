#!/bin/bash

set -e  # Прерывать выполнение при ошибках

echo "Остановка незавершенных процессов"
pkill -f 'uvicorn app.main:app' || echo "Процессы не найдены"

echo "Переход в рабочий каталог"
cd "/home/alexandre/Рабочий стол/chrome-lg/backend_lg" || {
    echo "Ошибка: не удалось перейти в каталог"
    exit 1
}

echo "Проверка виртуального окружения"
if [ ! -f ".venv/bin/activate" ]; then
    echo "Ошибка: виртуальное окружение не найдено"
    exit 1
fi

echo "Активация виртуального окружения"
source .venv/bin/activate

echo "Проверка установки uvicorn"
if ! python -c "import uvicorn" 2>/dev/null; then
    echo "Ошибка: uvicorn не установлен"
    exit 1
fi

echo "Запуск сервера"
uvicorn app.main:app --host 127.0.0.1 --port 8010
