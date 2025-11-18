#!/bin/bash

# Запрашиваем данные у пользователя
read -p "Введите имя базы данных: " DB_NAME
read -p "Введите имя пользователя базы данных: " DB_USER
read -s -p "Введите пароль пользователя базы данных: " DB_PASSWORD
echo

# Создаем базу данных и пользователя
sudo -u postgres psql << EOF
CREATE DATABASE $DB_NAME;
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
EOF

# Обновляем .env файл
echo "DJANGO_ENV=production" >> .env
echo "DB_NAME=$DB_NAME" >> .env
echo "DB_USER=$DB_USER" >> .env
echo "DB_PASSWORD=$DB_PASSWORD" >> .env
echo "DB_HOST=localhost" >> .env
echo "DB_PORT=5432" >> .env

echo "База данных создана и настройки добавлены в .env файл"