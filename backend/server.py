import os
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict
import logging

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from enum import Enum

# Mongo
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection

# Telegram Bot (python-telegram-bot v21+)
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    ContextTypes, filters
)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# Enums and Constants
# -----------------------------
class UserRole(str, Enum):
    CLIENT = "client"       # Заказчик
    WORKER = "worker"       # Исполнитель
    ADMIN = "admin"         # Администратор
    MODERATOR = "moderator" # Модератор

class WorkerType(str, Enum):
    LOADER = "loader"
    DRIVER = "driver"
    RIGGER = "rigger"
    CLEANER = "cleaner"
    HANDYMAN = "handyman"

class TaskStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    PUBLISHED = "published"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    URGENT = "urgent"

class TaskType(str, Enum):
    LOADING = "loading"
    MOVING = "moving"
    CLEANING = "cleaning"
    DELIVERY = "delivery"
    ASSEMBLY = "assembly"
    OTHER = "other"

# -----------------------------
# Config & Globals
# -----------------------------
MONGO_URL = os.environ.get("MONGO_URL")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TOKEN")
WEBAPP_BASE_URL = os.environ.get("WEBAPP_BASE_URL")  # HTTPS URL for Telegram WebApp button

DB_NAME = os.environ.get("DB_NAME", "workersystem")
COLLECTION_USERS = "users"
COLLECTION_TASKS = "tasks"
COLLECTION_APPLICATIONS = "applications"
COLLECTION_REMINDERS = "reminders"
COLLECTION_CHATS = "chats"
COLLECTION_PAYMENTS = "payments"

# FastAPI app
app = FastAPI(title="Workers System Backend")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates and Static
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Template filters

def format_currency(amount):
    if amount is None:
        return "0 ₽"
    try:
        return f"{int(amount):,} ₽".replace(",", " ")
    except Exception:
        return f"{amount} ₽"

def format_datetime(date_str):
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(str(date_str).replace('Z', '+00:00'))
        return dt.strftime('%d.%m.%Y %H:%M')
    except Exception:
        return str(date_str)

def format_date(date_str):
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(str(date_str).replace('Z', '+00:00'))
        return dt.strftime('%d.%m.%Y')
    except Exception:
        return str(date_str)

templates.env.filters["format_currency"] = format_currency
templates.env.filters["format_datetime"] = format_datetime
templates.env.filters["format_date"] = format_date

# API router (all routes must be under /api)
api = APIRouter(prefix="/api")

# Mongo globals
mongo_client: Optional[AsyncIOMotorClient] = None
db: Optional[AsyncIOMotorDatabase] = None
users_col: Optional[AsyncIOMotorCollection] = None
tasks_col: Optional[AsyncIOMotorCollection] = None
applications_col: Optional[AsyncIOMotorCollection] = None
reminders_col: Optional[AsyncIOMotorCollection] = None
chats_col: Optional[AsyncIOMotorCollection] = None
payments_col: Optional[AsyncIOMotorCollection] = None

# Telegram Application placeholder
telegram_app: Optional[Application] = None

# -----------------------------
# Models
# -----------------------------
class WorkerProfile(BaseModel):
    worker_types: List[WorkerType] = []
    rating: float = 5.0
    completed_tasks: int = 0
    cancelled_tasks: int = 0
    on_vacation: bool = False
    vacation_start: Optional[str] = None
    vacation_end: Optional[str] = None
    metro_stations: List[str] = []
    work_schedule: Dict = {}
    special_skills: Dict = {}

class ClientProfile(BaseModel):
    company_name: Optional[str] = None
    total_orders: int = 0
    total_spent: float = 0.0
    rating: float = 5.0

class UserOut(BaseModel):
    id: str
    tg_chat_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    role: UserRole
    is_active: bool
    is_verified: bool
    worker_profile: Optional[WorkerProfile] = None
    client_profile: Optional[ClientProfile] = None
    created_at: str

class TaskRequirement(BaseModel):
    worker_type: WorkerType
    count: int
    hourly_rate: Optional[float] = None

class TaskBase(BaseModel):
    title: str
    description: str
    task_type: TaskType
    requirements: List[TaskRequirement] = []
    location: str
    metro_station: Optional[str] = None
    start_datetime: str
    duration_hours: int = Field(ge=4, le=24)
    client_price: float = Field(gt=0)
    worker_price: Optional[float] = None
    verified_only: bool = False
    additional_info: Optional[str] = None

class TaskCreate(TaskBase):
    client_id: str

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    worker_price: Optional[float] = None
    moderation_notes: Optional[str] = None

class TaskOut(BaseModel):
    id: str
    title: str
    description: str
    task_type: TaskType
    requirements: List[TaskRequirement]
    location: str
    metro_station: Optional[str] = None
    start_datetime: str
    duration_hours: int
    client_price: float
    worker_price: Optional[float] = None
    verified_only: bool
    status: TaskStatus
    client_id: str
    assigned_workers: List[str] = []
    applications_count: int = 0
    created_at: str
    updated_at: str

class ReminderCreate(BaseModel):
    user_id: str
    title: str
    description: Optional[str] = None
    remind_at: str
    task_id: Optional[str] = None

class ReminderOut(BaseModel):
    id: str
    user_id: str
    title: str
    description: Optional[str] = None
    remind_at: str
    task_id: Optional[str] = None
    is_sent: bool = False
    created_at: str

# -----------------------------
# Dependencies
# -----------------------------
async def get_users_col() -> AsyncIOMotorCollection:
    if users_col is None:
        raise HTTPException(status_code=500, detail="Database is not initialized")
    return users_col

async def get_tasks_col() -> AsyncIOMotorCollection:
    if tasks_col is None:
        raise HTTPException(status_code=500, detail="Database is not initialized")
    return tasks_col

async def get_reminders_col() -> AsyncIOMotorCollection:
    if reminders_col is None:
        raise HTTPException(status_code=500, detail="Database is not initialized")
    return reminders_col

# -----------------------------
# API Routes (/api)
# -----------------------------
@api.get("/health")
async def health():
    db_connected = False
    try:
        if db is not None:
            await db.command("ping")
            db_connected = True
    except Exception as e:
        logger.error(f"DB ping failed: {e}")
    return {
        "ok": True,
        "service": "backend",
        "db_connected": db_connected,
        "time": datetime.now(timezone.utc).isoformat(),
    }

# Users
@api.get("/users", response_model=List[UserOut])
async def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    role: Optional[UserRole] = None,
    col: AsyncIOMotorCollection = Depends(get_users_col),
):
    filter_query = {}
    if role:
        filter_query["role"] = role
    cursor = col.find(filter_query).sort("created_at", -1).skip(offset).limit(limit)
    results: List[UserOut] = []
    async for doc in cursor:
        results.append(UserOut(**doc))
    return results

# Tasks
@api.post("/tasks", response_model=TaskOut)
async def create_task(payload: TaskCreate, col: AsyncIOMotorCollection = Depends(get_tasks_col)):
    task_id = uuid.uuid4().hex
    doc = {
        "id": task_id,
        "title": payload.title,
        "description": payload.description,
        "task_type": payload.task_type,
        "requirements": [r.dict() for r in payload.requirements],
        "location": payload.location,
        "metro_station": payload.metro_station,
        "start_datetime": payload.start_datetime,
        "duration_hours": payload.duration_hours,
        "client_price": payload.client_price,
        "worker_price": payload.worker_price,
        "verified_only": payload.verified_only,
        "additional_info": payload.additional_info,
        "status": TaskStatus.PENDING,
        "client_id": payload.client_id,
        "assigned_workers": [],
        "applications_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await col.insert_one(doc)
    return TaskOut(**doc)

@api.get("/tasks", response_model=List[TaskOut])
async def list_tasks(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[TaskStatus] = None,
    task_type: Optional[TaskType] = None,
    client_id: Optional[str] = None,
    col: AsyncIOMotorCollection = Depends(get_tasks_col),
):
    filter_query = {}
    if status:
        filter_query["status"] = status
    if task_type:
        filter_query["task_type"] = task_type
    if client_id:
        filter_query["client_id"] = client_id
    cursor = col.find(filter_query).sort("created_at", -1).skip(offset).limit(limit)
    results: List[TaskOut] = []
    async for doc in cursor:
        results.append(TaskOut(**doc))
    return results

@api.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: str, col: AsyncIOMotorCollection = Depends(get_tasks_col)):
    doc = await col.find_one({"id": task_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskOut(**doc)

@api.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(task_id: str, payload: TaskUpdate, col: AsyncIOMotorCollection = Depends(get_tasks_col)):
    update_fields = {k: v for k, v in payload.dict().items() if v is not None}
    if not update_fields:
        doc = await col.find_one({"id": task_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Task not found")
        return TaskOut(**doc)
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    from pymongo import ReturnDocument
    res = await col.find_one_and_update({"id": task_id}, {"$set": update_fields}, return_document=ReturnDocument.AFTER)
    if not res:
        await col.update_one({"id": task_id}, {"$set": update_fields})
        res = await col.find_one({"id": task_id})
    if not res:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskOut(**res)

# Reminders
@api.post("/reminders", response_model=ReminderOut)
async def create_reminder(payload: ReminderCreate):
    if reminders_col is None:
        raise HTTPException(status_code=500, detail="Database is not initialized")
    reminder_id = uuid.uuid4().hex
    doc = {
        "id": reminder_id,
        "user_id": payload.user_id,
        "title": payload.title,
        "description": payload.description,
        "remind_at": payload.remind_at,
        "task_id": payload.task_id,
        "is_sent": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await reminders_col.insert_one(doc)
    return ReminderOut(**doc)

@api.get("/reminders", response_model=List[ReminderOut])
async def list_reminders(user_id: Optional[str] = None, limit: int = Query(50, ge=1, le=200)):
    if reminders_col is None:
        raise HTTPException(status_code=500, detail="Database is not initialized")
    filter_query = {}
    if user_id:
        filter_query["user_id"] = user_id
    cursor = reminders_col.find(filter_query).sort("remind_at", 1).limit(limit)
    results: List[ReminderOut] = []
    async for doc in cursor:
        results.append(ReminderOut(**doc))
    return results

@api.get("/stats/summary")
async def stats_summary():
    try:
        if not tasks_col or not users_col:
            return {
                "total_tasks": 0,
                "by_status": {},
                "total_revenue": 0,
                "total_users": 0,
                "workers_count": 0,
                "clients_count": 0,
            }
        total_tasks = await tasks_col.count_documents({})
        by_status = {}
        for status in TaskStatus:
            by_status[status.value] = await tasks_col.count_documents({"status": status.value})
        agg = tasks_col.aggregate([
            {"$match": {"status": TaskStatus.COMPLETED}},
            {"$group": {"_id": None, "sum": {"$sum": "$client_price"}}},
        ])
        total_revenue = 0
        async for x in agg:
            total_revenue = x.get("sum", 0)
        total_users = await users_col.count_documents({})
        workers_count = await users_col.count_documents({"role": UserRole.WORKER})
        clients_count = await users_col.count_documents({"role": UserRole.CLIENT})
        return {
            "total_tasks": total_tasks,
            "by_status": by_status,
            "total_revenue": int(total_revenue),
            "total_users": total_users,
            "workers_count": workers_count,
            "clients_count": clients_count,
        }
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return {
            "total_tasks": 0,
            "by_status": {},
            "total_revenue": 0,
            "total_users": 0,
            "workers_count": 0,
            "clients_count": 0,
        }

# Attach router
app.include_router(api)

# -----------------------------
# Frontend HTML Routes
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    try:
        stats = await stats_summary()
    except Exception:
        stats = {}
    return templates.TemplateResponse("dashboard.html", {"request": request, "stats": stats})

@app.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request, status: Optional[str] = None):
    tasks = []
    try:
        if tasks_col:
            tasks = await list_tasks(50, 0, status, None, None, tasks_col)  # type: ignore
    except Exception as e:
        logger.warning(f"Orders page fallback: {e}")
    return templates.TemplateResponse("orders.html", {"request": request, "tasks": tasks, "current_filter": status})

@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, role: Optional[str] = None):
    users = []
    try:
        if users_col:
            users = await list_users(50, 0, role, users_col)  # type: ignore
    except Exception as e:
        logger.warning(f"Users page fallback: {e}")
    return templates.TemplateResponse("users.html", {"request": request, "users": users, "current_filter": role})

@app.get("/moderation", response_class=HTMLResponse)
async def moderation_page(request: Request):
    tasks = []
    try:
        if tasks_col:
            tasks = await list_tasks(50, 0, TaskStatus.PENDING, None, None, tasks_col)  # type: ignore
    except Exception as e:
        logger.warning(f"Moderation page fallback: {e}")
    return templates.TemplateResponse("moderation.html", {"request": request, "tasks": tasks})

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    try:
        health_info = await health()
    except Exception:
        health_info = None
    return templates.TemplateResponse("settings.html", {"request": request, "health": health_info})

@app.get("/webapp", response_class=HTMLResponse)
async def webapp_page(request: Request, user_id: str = Query(...), tab: str = Query("tasks")):
    tasks = []
    reminders = []
    try:
        if tab == "tasks" and tasks_col:
            tasks = await list_tasks(50, 0, None, None, user_id, tasks_col)  # type: ignore
        elif tab == "reminders" and reminders_col:
            reminders = await list_reminders(user_id, 50)  # type: ignore
    except Exception as e:
        logger.warning(f"Webapp load error: {e}")
    return templates.TemplateResponse("webapp.html", {
        "request": request,
        "user_id": user_id,
        "active_tab": tab,
        "tasks": tasks,
        "reminders": reminders,
    })

# -----------------------------
# Telegram Bot Handlers (Start, Profile, Create Task Conversation)
# -----------------------------
MAIN_MENU, TASK_TITLE, TASK_DESC, TASK_LOCATION, TASK_DATETIME, TASK_DURATION, TASK_PRICE, TASK_CONFIRM = range(8)

MAIN_KEYBOARD = [
    ["📋 Мои задания", "🔍 Поиск заданий"],
    ["➕ Создать задание", "👤 Профиль"],
    ["⏰ Напоминания", "💬 Поддержка"],
    ["⚙️ Настройки"],
]

async def ensure_user(update: Update, default_role: UserRole = UserRole.WORKER) -> Optional[str]:
    """Create or update user in DB, return user id"""
    global users_col
    if users_col is None:
        return None
    user = update.effective_user
    chat_id = update.effective_chat.id
    existing = await users_col.find_one({"tg_chat_id": chat_id})
    if existing:
        await users_col.update_one({"tg_chat_id": chat_id}, {"$set": {
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }})
        return existing["id"]
    new_id = uuid.uuid4().hex
    doc = {
        "id": new_id,
        "tg_chat_id": chat_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": None,
        "role": default_role,
        "is_active": True,
        "is_verified": False,
        "worker_profile": WorkerProfile().dict() if default_role == UserRole.WORKER else None,
        "client_profile": ClientProfile().dict() if default_role == UserRole.CLIENT else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await users_col.insert_one(doc)
    return new_id

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await ensure_user(update)
    welcome_text = (
        "🏢 Добро пожаловать в систему!")
    # Simple menu
    await update.message.reply_text(welcome_text)
    await update.message.reply_text(
        "Основное меню:",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True),
    )
    return MAIN_MENU

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if users_col is None:
        await update.message.reply_text("❌ База данных недоступна")
        return MAIN_MENU
    chat_id = update.effective_chat.id
    user = await users_col.find_one({"tg_chat_id": chat_id})
    if not user:
        await update.message.reply_text("❌ Профиль не найден")
        return MAIN_MENU
    role_label = {
        "worker": "Исполнитель",
        "client": "Заказчик",
        "admin": "Администратор",
        "moderator": "Модератор",
    }.get(user.get("role"), user.get("role"))
    text = (
        f"👤 Профиль\n\n"
        f"Имя: {user.get('first_name', '')} {user.get('last_name', '')}\n"
        f"Логин: @{user.get('username', '—')}\n"
        f"Роль: {role_label}\n"
        f"Статус: {'Верифицирован' if user.get('is_verified') else 'Не верифицирован'}\n"
    )
    if user.get("role") == "worker" and user.get("worker_profile"):
        wp = user["worker_profile"]
        text += (
            f"Рейтинг: {wp.get('rating', 5.0)}⭐\n"
            f"Выполнено: {wp.get('completed_tasks', 0)}\n"
            f"Отменено: {wp.get('cancelled_tasks', 0)}\n"
        )
    await update.message.reply_text(text)
    return MAIN_MENU

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "👤 Профиль":
        return await show_profile(update, context)
    if text == "➕ Создать задание":
        context.user_data.clear()
        await update.message.reply_text("Введите название задания:")
        return TASK_TITLE
    if text == "📋 Мои задания":
        if tasks_col is None or users_col is None:
            await update.message.reply_text("❌ База данных недоступна")
            return MAIN_MENU
        user = await users_col.find_one({"tg_chat_id": update.effective_chat.id})
        if not user:
            await update.message.reply_text("❌ Пользователь не найден")
            return MAIN_MENU
        # For client show their tasks, for worker assigned
        query = {"client_id": user["id"]} if user["role"] == "client" else {"assigned_workers": user["id"]}
        cursor = tasks_col.find(query).sort("created_at", -1).limit(10)
        tasks = []
        async for d in cursor:
            tasks.append(d)
        if not tasks:
            await update.message.reply_text("У вас пока нет заданий")
            return MAIN_MENU
        msg = "📋 Мои задания\n\n"
        for t in tasks:
            msg += f"• {t['title']} — {t.get('status', 'draft')} — {t.get('client_price', 0)}₽\n"
        await update.message.reply_text(msg)
        return MAIN_MENU
    # Fallback
    await update.message.reply_text(
        "Пожалуйста, выберите действие из меню:",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True),
    )
    return MAIN_MENU

# Create Task conversation steps
async def handle_task_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["title"] = update.message.text.strip()
    await update.message.reply_text("Опишите задание:")
    return TASK_DESC

async def handle_task_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["description"] = update.message.text.strip()
    await update.message.reply_text("Укажите адрес выполнения:")
    return TASK_LOCATION

async def handle_task_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["location"] = update.message.text.strip()
    await update.message.reply_text("Введите дату и время начала (формат ГГГГ-ММ-ДД ЧЧ:ММ):")
    return TASK_DATETIME

async def handle_task_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        # Accept "YYYY-MM-DD HH:MM"
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
        context.user_data["start_datetime"] = dt.replace(tzinfo=timezone.utc).isoformat()
    except Exception:
        await update.message.reply_text("Неверный формат. Пример: 2025-03-01 09:00")
        return TASK_DATETIME
    # Duration keyboard 4..24
    hours = [str(h) for h in range(4, 25)]
    keyboard = [[h for h in hours[i:i+6]] for i in range(0, len(hours), 6)]
    await update.message.reply_text(
        "Выберите продолжительность (часы):",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )
    return TASK_DURATION

async def handle_task_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        duration = int(update.message.text.strip())
        if duration < 4 or duration > 24:
            raise ValueError
        context.user_data["duration_hours"] = duration
    except Exception:
        await update.message.reply_text("Пожалуйста, выберите число от 4 до 24")
        return TASK_DURATION
    await update.message.reply_text(
        "Укажите бюджет (₽):",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True),
    )
    return TASK_PRICE

async def handle_task_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip().replace(" ", ""))
        if price <= 0:
            raise ValueError
        context.user_data["client_price"] = price
    except Exception:
        await update.message.reply_text("Введите положительное число, например 5000")
        return TASK_PRICE

    # Save task to DB
    if tasks_col is None or users_col is None:
        await update.message.reply_text("❌ База данных недоступна")
        return MAIN_MENU

    user = await users_col.find_one({"tg_chat_id": update.effective_chat.id})
    if not user:
        await update.message.reply_text("❌ Пользователь не найден")
        return MAIN_MENU

    payload = {
        "title": context.user_data["title"],
        "description": context.user_data["description"],
        "task_type": TaskType.LOADING,
        "requirements": [{"worker_type": WorkerType.LOADER, "count": 1}],
        "location": context.user_data["location"],
        "metro_station": None,
        "start_datetime": context.user_data["start_datetime"],
        "duration_hours": context.user_data["duration_hours"],
        "client_price": context.user_data["client_price"],
        "worker_price": None,
        "verified_only": False,
        "additional_info": None,
        "client_id": user["id"],
    }

    try:
        await create_task(TaskCreate(**payload), tasks_col)  # type: ignore
        await update.message.reply_text("✅ Задание создано и отправлено на модерацию!")
    except Exception as e:
        logger.error(f"Create task error: {e}")
        await update.message.reply_text("❌ Ошибка при создании задания")
    finally:
        context.user_data.clear()
    return MAIN_MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Диалог завершён.",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True),
    )
    return MAIN_MENU

# -----------------------------
# Startup & Shutdown
# -----------------------------
@app.on_event("startup")
async def on_startup():
    global mongo_client, db, users_col, tasks_col, applications_col, reminders_col, chats_col, payments_col, telegram_app
    # MongoDB
    if MONGO_URL:
        try:
            mongo_client = AsyncIOMotorClient(MONGO_URL)
            db = mongo_client[DB_NAME]
            users_col = db[COLLECTION_USERS]
            tasks_col = db[COLLECTION_TASKS]
            applications_col = db[COLLECTION_APPLICATIONS]
            reminders_col = db[COLLECTION_REMINDERS]
            chats_col = db[COLLECTION_CHATS]
            payments_col = db[COLLECTION_PAYMENTS]
            # Indexes
            await users_col.create_index("id", unique=True)
            await users_col.create_index("tg_chat_id", unique=True)
            await tasks_col.create_index("id", unique=True)
            await tasks_col.create_index("client_id")
            await tasks_col.create_index("status")
            await reminders_col.create_index("id", unique=True)
            await reminders_col.create_index("user_id")
            await reminders_col.create_index("remind_at")
            logger.info("✅ MongoDB connected and indexes ensured")
        except Exception as e:
            logger.error(f"MongoDB connection failed: {e}")
    else:
        logger.warning("MONGO_URL is not set. Running with limited functionality.")

    # Telegram Bot - start only if token present; keep lightweight
    if TELEGRAM_BOT_TOKEN:
        try:
            telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
            conv = ConversationHandler(
                entry_points=[CommandHandler("start", cmd_start)],
                states={
                    MAIN_MENU: [MessageHandler(filters.TEXT & (~filters.COMMAND), main_menu_handler)],
                    TASK_TITLE: [MessageHandler(filters.TEXT & (~filters.COMMAND), handle_task_title)],
                    TASK_DESC: [MessageHandler(filters.TEXT & (~filters.COMMAND), handle_task_desc)],
                    TASK_LOCATION: [MessageHandler(filters.TEXT & (~filters.COMMAND), handle_task_location)],
                    TASK_DATETIME: [MessageHandler(filters.TEXT & (~filters.COMMAND), handle_task_datetime)],
                    TASK_DURATION: [MessageHandler(filters.TEXT & (~filters.COMMAND), handle_task_duration)],
                    TASK_PRICE: [MessageHandler(filters.TEXT & (~filters.COMMAND), handle_task_price)],
                },
                fallbacks=[CommandHandler("cancel", cancel)],
            )
            telegram_app.add_handler(conv)
            telegram_app.add_handler(CommandHandler("cancel", cancel))

            await telegram_app.initialize()
            await telegram_app.start()
            # For v21, prefer run_polling in standalone; here we just start and do not block
            logger.info("🤖 Telegram bot initialized")
        except Exception as e:
            logger.error(f"Telegram bot init failed: {e}")

@app.on_event("shutdown")
async def on_shutdown():
    global telegram_app, mongo_client
    if telegram_app is not None:
        try:
            await telegram_app.stop()
            logger.info("🤖 Telegram bot stopped")
        except Exception as e:
            logger.error(f"Error stopping telegram app: {e}")
    if mongo_client is not None:
        try:
            mongo_client.close()
            logger.info("🗄️ MongoDB connection closed")
        except Exception as e:
            logger.error(f"Error closing MongoDB: {e}")