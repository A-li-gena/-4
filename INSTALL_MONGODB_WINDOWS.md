# MongoDB Installation Guide for Windows

## Способ 1: Установка MongoDB Community Server

1. Перейдите на https://www.mongodb.com/try/download/community
2. Выберите:
   - Version: 7.0 (или последнюю)
   - Platform: Windows x64
   - Package: msi

3. Скачайте и запустите установщик

4. В процессе установки:
   - ✅ Выберите "Complete" setup
   - ✅ Установите "MongoDB as a Service"
   - ✅ Отметьте "Run service as Network Service user"
   - ✅ Установите MongoDB Compass (GUI инструмент)

5. После установки MongoDB автоматически запустится как служба Windows

## Способ 2: Через Chocolatey (если установлен)

```powershell
# Открыть PowerShell как Администратор
choco install mongodb

# Запустить службу
net start MongoDB
```

## Способ 3: Portable версия (самый простой)

1. Создайте папку C:\mongodb
2. Скачайте ZIP архив MongoDB с официального сайта
3. Распакуйте в C:\mongodb
4. Создайте папку C:\mongodb\data\db
5. Запустите в командной строке:

```cmd
cd C:\mongodb\bin
mongod.exe --dbpath C:\mongodb\data\db
```

## Проверка установки:

```cmd
# В новом окне командной строки
mongosh
# Должно подключиться к MongoDB
```

## Альтернатива: Docker (если установлен)

```powershell
docker run -d -p 27017:27017 --name mongodb-workers mongo:latest
```