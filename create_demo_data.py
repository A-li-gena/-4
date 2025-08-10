#!/usr/bin/env python3
"""
Demo Data Creator for Workers System
Создает тестовые данные в MongoDB
"""

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient

# Подключение к MongoDB
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "workersystem"

async def create_demo_data():
    print("🚀 Создаем демо данные для Workers System...")
    
    # Подключение к MongoDB
    mongo_client = AsyncIOMotorClient(MONGO_URL)
    db = mongo_client[DB_NAME]
    
    try:
        # Проверка подключения
        await db.command("ping")
        print("✅ Подключение к MongoDB успешно")
    except Exception as e:
        print(f"❌ Ошибка подключения к MongoDB: {e}")
        return
    
    users_col = db.users
    tasks_col = db.tasks
    
    # Очищаем старые данные
    await users_col.delete_many({})
    await tasks_col.delete_many({})
    print("🗑️ Старые данные удалены")
    
    # Создаем пользователей
    demo_users = []
    
    # Администратор
    admin_id = uuid.uuid4().hex
    admin = {
        "id": admin_id,
        "tg_chat_id": 123456789,
        "username": "admin",
        "first_name": "Администратор",
        "last_name": "Системы",
        "phone": "+7 (999) 123-45-67",
        "role": "admin",
        "is_active": True,
        "is_verified": True,
        "worker_profile": None,
        "client_profile": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    demo_users.append(admin)
    
    # Клиенты
    clients = [
        {
            "username": "client1",
            "first_name": "Иван",
            "last_name": "Петров",
            "company": "ООО Переезды",
            "phone": "+7 (999) 111-22-33"
        },
        {
            "username": "client2", 
            "first_name": "Мария",
            "last_name": "Сидорова",
            "company": "ИП Сидорова",
            "phone": "+7 (999) 444-55-66"
        }
    ]
    
    client_ids = []
    for i, client_data in enumerate(clients):
        client_id = uuid.uuid4().hex
        client_ids.append(client_id)
        
        client = {
            "id": client_id,
            "tg_chat_id": 200000000 + i,
            "username": client_data["username"],
            "first_name": client_data["first_name"],
            "last_name": client_data["last_name"],
            "phone": client_data["phone"],
            "role": "client",
            "is_active": True,
            "is_verified": True,
            "worker_profile": None,
            "client_profile": {
                "company_name": client_data["company"],
                "total_orders": i * 3 + 2,
                "total_spent": (i + 1) * 15000.0,
                "rating": 4.8 - i * 0.2
            },
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        demo_users.append(client)
    
    # Исполнители
    workers = [
        {
            "username": "worker1",
            "first_name": "Алексей",
            "last_name": "Грузчиков",
            "worker_types": ["loader"],
            "rating": 4.9,
            "completed": 25
        },
        {
            "username": "worker2",
            "first_name": "Дмитрий", 
            "last_name": "Водителев",
            "worker_types": ["driver", "loader"],
            "rating": 4.7,
            "completed": 18
        },
        {
            "username": "worker3",
            "first_name": "Сергей",
            "last_name": "Такелажников",
            "worker_types": ["rigger", "loader"],
            "rating": 5.0,
            "completed": 32
        },
        {
            "username": "worker4",
            "first_name": "Антон",
            "last_name": "Уборщиков",
            "worker_types": ["cleaner"],
            "rating": 4.6,
            "completed": 12
        }
    ]
    
    worker_ids = []
    for i, worker_data in enumerate(workers):
        worker_id = uuid.uuid4().hex
        worker_ids.append(worker_id)
        
        worker = {
            "id": worker_id,
            "tg_chat_id": 300000000 + i,
            "username": worker_data["username"],
            "first_name": worker_data["first_name"],
            "last_name": worker_data["last_name"],
            "phone": f"+7 (999) {700 + i:03d}-{(i+1)*11:02d}-{(i+2)*22:02d}",
            "role": "worker",
            "is_active": True,
            "is_verified": True,
            "worker_profile": {
                "worker_types": worker_data["worker_types"],
                "rating": worker_data["rating"],
                "completed_tasks": worker_data["completed"],
                "cancelled_tasks": i,
                "on_vacation": False,
                "vacation_start": None,
                "vacation_end": None,
                "metro_stations": [
                    ["Сокольники", "Красносельская", "Комсомольская"][i % 3],
                    ["Парк культуры", "Кропоткинская", "Охотный ряд"][(i+1) % 3]
                ],
                "work_schedule": {
                    "monday": {"available": True, "hours": "09:00-18:00"},
                    "tuesday": {"available": True, "hours": "09:00-18:00"},
                    "wednesday": {"available": True, "hours": "09:00-18:00"},
                    "thursday": {"available": True, "hours": "09:00-18:00"},
                    "friday": {"available": True, "hours": "09:00-18:00"},
                    "saturday": {"available": i % 2 == 0, "hours": "10:00-16:00"},
                    "sunday": {"available": False, "hours": None}
                },
                "special_skills": {
                    "has_belts": "rigger" in worker_data["worker_types"],
                    "has_transport": "driver" in worker_data["worker_types"],
                    "experience_years": i + 2
                }
            },
            "client_profile": None,
            "created_at": (datetime.now(timezone.utc) - timedelta(days=30-i*5)).isoformat()
        }
        demo_users.append(worker)
    
    # Сохраняем пользователей
    await users_col.insert_many(demo_users)
    print(f"👥 Создано {len(demo_users)} пользователей")
    
    # Создаем задания
    demo_tasks = []
    
    task_templates = [
        {
            "title": "Погрузка мебели при переезде",
            "description": "Требуется погрузить мебель из 3-комнатной квартиры в грузовик. Мебель: диван, шкаф, комод, стол, стулья.",
            "task_type": "moving",
            "location": "Москва, ул. Тверская, 10",
            "metro_station": "Охотный ряд",
            "requirements": [{"worker_type": "loader", "count": 2, "hourly_rate": 500.0}],
            "duration_hours": 4,
            "client_price": 4000.0,
            "status": "pending"
        },
        {
            "title": "Разгрузка стройматериалов",
            "description": "Разгрузить кирпич, цемент и другие строительные материалы. Общий вес около 2 тонн.",
            "task_type": "loading",
            "location": "Москва, Стройплощадка на Ленинском проспекте",
            "metro_station": "Академическая",
            "requirements": [
                {"worker_type": "loader", "count": 3, "hourly_rate": 600.0},
                {"worker_type": "rigger", "count": 1, "hourly_rate": 800.0}
            ],
            "duration_hours": 6,
            "client_price": 12000.0,
            "status": "published"
        },
        {
            "title": "Уборка офиса после ремонта",
            "description": "Генеральная уборка офиса площадью 200 кв.м после завершения ремонтных работ.",
            "task_type": "cleaning", 
            "location": "Москва, Деловой центр Москва-Сити",
            "metro_station": "Деловой центр",
            "requirements": [{"worker_type": "cleaner", "count": 2, "hourly_rate": 400.0}],
            "duration_hours": 8,
            "client_price": 6400.0,
            "status": "published"
        },
        {
            "title": "Сборка мебели IKEA",
            "description": "Сборка кухонного гарнитура, 2 шкафов и обеденного стола из IKEA по инструкции.",
            "task_type": "assembly",
            "location": "Москва, Новые Черемушки",
            "metro_station": "Калужская",
            "requirements": [{"worker_type": "handyman", "count": 1, "hourly_rate": 700.0}],
            "duration_hours": 6,
            "client_price": 4200.0,
            "status": "completed"
        },
        {
            "title": "СРОЧНО! Нужен дополнительный грузчик",
            "description": "К уже работающей бригаде срочно нужен еще один грузчик. Переезд затягивается.",
            "task_type": "moving",
            "location": "Москва, Арбат",
            "metro_station": "Арбатская",
            "requirements": [{"worker_type": "loader", "count": 1, "hourly_rate": 550.0}],
            "duration_hours": 4,
            "client_price": 2500.0,
            "status": "urgent"
        }
    ]
    
    for i, task_template in enumerate(task_templates):
        task_id = uuid.uuid4().hex
        
        # Выбираем случайного клиента
        client_id = client_ids[i % len(client_ids)]
        
        # Рассчитываем дату задания
        if task_template["status"] == "completed":
            start_date = datetime.now(timezone.utc) - timedelta(days=i*2+1)
        else:
            start_date = datetime.now(timezone.utc) + timedelta(days=i+1, hours=i*2)
        
        task = {
            "id": task_id,
            "title": task_template["title"],
            "description": task_template["description"],
            "task_type": task_template["task_type"],
            "requirements": task_template["requirements"],
            "location": task_template["location"],
            "metro_station": task_template["metro_station"],
            "start_datetime": start_date.isoformat(),
            "duration_hours": task_template["duration_hours"],
            "client_price": task_template["client_price"],
            "worker_price": task_template["client_price"] * 0.8,  # 80% от цены клиента
            "verified_only": i % 3 == 0,  # Каждое третье задание только для проверенных
            "status": task_template["status"],
            "client_id": client_id,
            "assigned_workers": [worker_ids[0]] if task_template["status"] in ["completed", "in_progress"] else [],
            "applications_count": 0 if task_template["status"] in ["draft", "pending"] else i + 2,
            "created_at": (datetime.now(timezone.utc) - timedelta(hours=i*6)).isoformat(),
            "updated_at": (datetime.now(timezone.utc) - timedelta(hours=i*3)).isoformat(),
        }
        demo_tasks.append(task)
    
    # Сохраняем задания
    await tasks_col.insert_many(demo_tasks)
    print(f"📋 Создано {len(demo_tasks)} заданий")
    
    print("✅ Демо данные успешно созданы!")
    print("\n📊 Статистика:")
    print(f"   Пользователей: {len(demo_users)}")
    print(f"   - Администраторов: 1")
    print(f"   - Клиентов: {len(clients)}")  
    print(f"   - Исполнителей: {len(workers)}")
    print(f"   Заданий: {len(demo_tasks)}")
    
    status_counts = {}
    for task in demo_tasks:
        status = task["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    
    for status, count in status_counts.items():
        print(f"   - {status}: {count}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(create_demo_data())