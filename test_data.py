#!/usr/bin/env python3
"""
Скрипт для создания тестовых данных в системе
"""
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
import uuid

# Добавляем путь к backend для импорта моделей
sys.path.append('/app/backend')
from server import UserRole, WorkerType, TaskStatus, TaskType

# Конфигурация
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "workersystem"

async def create_test_data():
    """Создаем тестовые данные"""
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    # Коллекции
    users_col = db.users
    tasks_col = db.tasks
    reminders_col = db.reminders
    
    print("🗃️ Создание тестовых данных...")
    
    # 1. Создаем тестового пользователя-заказчика
    client_id = uuid.uuid4().hex
    client_user = {
        "id": client_id,
        "tg_chat_id": 123456789,
        "username": "test_client",
        "first_name": "Алексей",
        "last_name": "Иванов",
        "phone": "+7 (905) 123-45-67",
        "role": UserRole.CLIENT,
        "is_active": True,
        "is_verified": True,
        "client_profile": {
            "company_name": "ООО Альфа Переезды",
            "total_orders": 12,
            "total_spent": 45000.0,
            "rating": 4.8
        },
        "worker_profile": None,
        "created_at": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    }
    
    # 2. Создаем тестового исполнителя
    worker_id = uuid.uuid4().hex
    worker_user = {
        "id": worker_id,
        "tg_chat_id": 987654321,
        "username": "test_worker",
        "first_name": "Дмитрий",
        "last_name": "Петров",
        "phone": "+7 (911) 987-65-43",
        "role": UserRole.WORKER,
        "is_active": True,
        "is_verified": True,
        "worker_profile": {
            "worker_types": [WorkerType.LOADER, WorkerType.RIGGER],
            "rating": 4.9,
            "completed_tasks": 47,
            "cancelled_tasks": 2,
            "on_vacation": False,
            "vacation_start": None,
            "vacation_end": None,
            "metro_stations": ["Площадь Ленина", "Чернышевская", "Площадь Восстания"],
            "work_schedule": {},
            "special_skills": {"has_belts": True, "has_transport": False}
        },
        "client_profile": None,
        "created_at": (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    }
    
    # 3. Создаем админа
    admin_id = uuid.uuid4().hex
    admin_user = {
        "id": admin_id,
        "tg_chat_id": 111222333,
        "username": "admin",
        "first_name": "Администратор",
        "last_name": "Системы",
        "phone": "+7 (911) 111-22-33",
        "role": UserRole.ADMIN,
        "is_active": True,
        "is_verified": True,
        "worker_profile": None,
        "client_profile": None,
        "created_at": (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    }
    
    # Вставляем пользователей
    await users_col.insert_many([client_user, worker_user, admin_user])
    print(f"✅ Создано 3 тестовых пользователя")
    
    # 4. Создаем тестовые задания
    tasks = []
    
    # Активное задание на модерации
    task1_id = uuid.uuid4().hex
    task1 = {
        "id": task1_id,
        "title": "Разгрузка мебели из фуры",
        "description": "Требуется разгрузить 3-комнатную квартиру. Есть диван, шкаф, стол, стулья, коробки с вещами. Разгрузка на 3 этаж без лифта.",
        "task_type": TaskType.LOADING,
        "requirements": [
            {"worker_type": WorkerType.LOADER, "count": 3, "hourly_rate": None}
        ],
        "location": "СПб, Невский пр., 25",
        "metro_station": "Невский проспект",
        "start_datetime": (datetime.now(timezone.utc) + timedelta(days=2, hours=10)).isoformat(),
        "duration_hours": 4,
        "client_price": 4500.0,
        "worker_price": None,
        "verified_only": False,
        "additional_info": "Заказчик надежный, работает с нами уже 2 года",
        "status": TaskStatus.PENDING,
        "client_id": client_id,
        "assigned_workers": [],
        "applications_count": 0,
        "created_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        "updated_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    }
    
    # Опубликованное задание
    task2_id = uuid.uuid4().hex
    task2 = {
        "id": task2_id,
        "title": "Переезд офиса",
        "description": "Перевезти офисное оборудование: компьютеры, мониторы, принтеры, мебель. Упаковка предоставляется.",
        "task_type": TaskType.MOVING,
        "requirements": [
            {"worker_type": WorkerType.LOADER, "count": 2, "hourly_rate": None},
            {"worker_type": WorkerType.DRIVER, "count": 1, "hourly_rate": None}
        ],
        "location": "СПб, ул. Марата, 15",
        "metro_station": "Владимирская",
        "start_datetime": (datetime.now(timezone.utc) + timedelta(days=5, hours=9)).isoformat(),
        "duration_hours": 8,
        "client_price": 12000.0,
        "worker_price": 10000.0,
        "verified_only": True,
        "additional_info": "Много техники, нужны аккуратные исполнители",
        "status": TaskStatus.PUBLISHED,
        "client_id": client_id,
        "assigned_workers": [],
        "applications_count": 5,
        "created_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        "updated_at": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    }
    
    # Задание в работе
    task3_id = uuid.uuid4().hex
    task3 = {
        "id": task3_id,
        "title": "Уборка после ремонта",
        "description": "Генеральная уборка 2-комнатной квартиры после евроремонта. Нужно убрать строительную пыль, помыть окна, полы.",
        "task_type": TaskType.CLEANING,
        "requirements": [
            {"worker_type": WorkerType.CLEANER, "count": 2, "hourly_rate": None}
        ],
        "location": "СПб, пр. Просвещения, 67",
        "metro_station": "Проспект Просвещения",
        "start_datetime": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        "duration_hours": 6,
        "client_price": 6000.0,
        "worker_price": 5000.0,
        "verified_only": False,
        "additional_info": "Квартира новая, ремонт качественный",
        "status": TaskStatus.IN_PROGRESS,
        "client_id": client_id,
        "assigned_workers": [worker_id],
        "applications_count": 3,
        "created_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        "updated_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    }
    
    # Выполненное задание
    task4_id = uuid.uuid4().hex
    task4 = {
        "id": task4_id,
        "title": "Доставка стройматериалов",
        "description": "Доставить и разгрузить стройматериалы на объект: кирпич, цемент, арматура.",
        "task_type": TaskType.DELIVERY,
        "requirements": [
            {"worker_type": WorkerType.LOADER, "count": 3, "hourly_rate": None},
            {"worker_type": WorkerType.DRIVER, "count": 1, "hourly_rate": None}
        ],
        "location": "СПб, Индустриальный пр., 44",
        "metro_station": "Ладожская",
        "start_datetime": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "duration_hours": 5,
        "client_price": 8000.0,
        "worker_price": 6800.0,
        "verified_only": False,
        "additional_info": "Работа выполнена отлично, заказчик доволен",
        "status": TaskStatus.COMPLETED,
        "client_id": client_id,
        "assigned_workers": [worker_id],
        "applications_count": 7,
        "created_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
        "updated_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    }
    
    tasks = [task1, task2, task3, task4]
    await tasks_col.insert_many(tasks)
    print(f"✅ Создано {len(tasks)} тестовых заданий")
    
    # 5. Создаем тестовые напоминания
    reminders = []
    
    # Напоминание сегодня
    reminder1_id = uuid.uuid4().hex
    reminder1 = {
        "id": reminder1_id,
        "user_id": client_id,
        "title": "Подтвердить заказ на завтра",
        "description": "Связаться с исполнителями и подтвердить время начала работ",
        "remind_at": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
        "task_id": task2_id,
        "is_sent": False,
        "created_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    }
    
    # Напоминание завтра
    reminder2_id = uuid.uuid4().hex
    reminder2 = {
        "id": reminder2_id,
        "user_id": client_id,
        "title": "Встреча с клиентом",
        "description": "Обсудить детали переезда офиса и уточнить список оборудования",
        "remind_at": (datetime.now(timezone.utc) + timedelta(days=1, hours=9)).isoformat(),
        "task_id": None,
        "is_sent": False,
        "created_at": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    }
    
    # Напоминание для работника
    reminder3_id = uuid.uuid4().hex
    reminder3 = {
        "id": reminder3_id,
        "user_id": worker_id,
        "title": "Приехать на объект к 14:00",
        "description": "Не забыть захватить ремни и перчатки для такелажных работ",
        "remind_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "task_id": task1_id,
        "is_sent": False,
        "created_at": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    }
    
    reminders = [reminder1, reminder2, reminder3]
    await reminders_col.insert_many(reminders)
    print(f"✅ Создано {len(reminders)} тестовых напоминаний")
    
    print(f"\n🎉 Тестовые данные успешно созданы!")
    print(f"📋 Задания: {len(tasks)} шт")
    print(f"👥 Пользователи: 3 шт (заказчик, исполнитель, админ)")
    print(f"⏰ Напоминания: {len(reminders)} шт")
    
    print(f"\n🔗 Тестовый пользователь для WebApp:")
    print(f"   Заказчик ID: {client_id}")
    print(f"   WebApp URL: http://localhost:3000/webapp?user_id={client_id}")
    
    print(f"\n🤖 Тестовые Telegram чаты:")
    print(f"   Заказчик: {client_user['tg_chat_id']}")
    print(f"   Исполнитель: {worker_user['tg_chat_id']}")
    print(f"   Админ: {admin_user['tg_chat_id']}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(create_test_data())