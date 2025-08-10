import os
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, validator
from enum import Enum

# Mongo
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from dotenv import load_dotenv

# Telegram Bot (python-telegram-bot v21+)
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import (Application, CommandHandler, MessageHandler, ConversationHandler,
                          ContextTypes, filters, CallbackQueryHandler)

# -----------------------------
# Enums and Constants
# -----------------------------
class UserRole(str, Enum):
    CLIENT = "client"       # Заказчик
    WORKER = "worker"       # Исполнитель
    ADMIN = "admin"         # Администратор  
    MODERATOR = "moderator" # Модератор

class WorkerType(str, Enum):
    LOADER = "loader"           # Грузчик
    DRIVER = "driver"           # Водитель
    RIGGER = "rigger"           # Такелажник
    CLEANER = "cleaner"         # Уборщик
    HANDYMAN = "handyman"       # Разнорабочий

class TaskStatus(str, Enum):
    DRAFT = "draft"             # Черновик
    PENDING = "pending"         # Ожидает модерации
    APPROVED = "approved"       # Одобрено админом
    PUBLISHED = "published"     # Опубликовано
    IN_PROGRESS = "in_progress" # В работе
    COMPLETED = "completed"     # Выполнено
    CANCELLED = "cancelled"     # Отменено
    URGENT = "urgent"           # Срочно нужен +1 человек

class TaskType(str, Enum):
    LOADING = "loading"         # Погрузка/разгрузка
    MOVING = "moving"           # Переезд
    CLEANING = "cleaning"       # Уборка
    DELIVERY = "delivery"       # Доставка
    ASSEMBLY = "assembly"       # Сборка/разборка
    OTHER = "other"             # Другое

# -----------------------------
# Config & Globals
# -----------------------------
MONGO_URL = os.environ.get("MONGO_URL")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TOKEN")

# Update database name for the work system
DB_NAME = os.environ.get("DB_NAME", "workersystem")
COLLECTION_USERS = "users"
COLLECTION_TASKS = "tasks"
COLLECTION_APPLICATIONS = "applications"
COLLECTION_REMINDERS = "reminders"
COLLECTION_CHATS = "chats"
COLLECTION_PAYMENTS = "payments"

app = FastAPI(title="Workers System Python Backend")

# Templates and static files setup
# Templates and static files setup
TEMPLATES_DIR = "templates" if os.path.isdir("templates") else "."
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Mount static files only if directory exists
import os
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
else:
    print("[warning] Static directory not found, static files will not be served")

# Custom template filters
def format_currency(amount):
    if amount is None:
        return "0 ₽"
    return f"{int(amount):,} ₽".replace(",", " ")

def format_datetime(date_str):
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime('%d.%m.%Y %H:%M')
    except:
        return str(date_str)

def format_date(date_str):
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime('%d.%m.%Y')
    except:
        return str(date_str)

templates.env.filters["format_currency"] = format_currency
templates.env.filters["format_datetime"] = format_datetime
templates.env.filters["format_date"] = format_date

# All API routes must be under /api
api = APIRouter(prefix="/api")

# CORS (adjust if needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mongo client placeholders
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
class UserBase(BaseModel):
    tg_chat_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    role: UserRole
    is_active: bool = True
    is_verified: bool = False

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
    special_skills: Dict = {}  # Например, {"has_belts": True для такелажников}
    
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
    worker_price: Optional[float] = None  # Устанавливается после модерации
    verified_only: bool = False
    additional_info: Optional[str] = None  # Доп. информация для админов
    
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
# API Routes
# -----------------------------
@api.get("/health")
async def health():
    db_connected = False
    try:
        if db is not None:
            await db.command("ping")
            db_connected = True
    except Exception:
        db_connected = False
    return {"ok": True, "service": "backend", "db_connected": db_connected, "time": datetime.now(timezone.utc).isoformat()}

# User Management
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

# Task Management
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
    
    res = await col.find_one_and_update({"id": task_id}, {"$set": update_fields}, return_document=True)
    if not res:
        await col.update_one({"id": task_id}, {"$set": update_fields})
        res = await col.find_one({"id": task_id})
    if not res:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskOut(**res)

# Reminders
@api.post("/reminders", response_model=ReminderOut)
async def create_reminder(payload: ReminderCreate, col: AsyncIOMotorCollection = Depends(get_reminders_col)):
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
    await col.insert_one(doc)
    return ReminderOut(**doc)

@api.get("/reminders", response_model=List[ReminderOut])
async def list_reminders(
    user_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    col: AsyncIOMotorCollection = Depends(get_reminders_col),
):
    filter_query = {}
    if user_id:
        filter_query["user_id"] = user_id
    
    cursor = col.find(filter_query).sort("remind_at", 1).limit(limit)
    results: List[ReminderOut] = []
    async for doc in cursor:
        results.append(ReminderOut(**doc))
    return results

@api.get("/stats/summary")
async def stats_summary(
    tasks_col: AsyncIOMotorCollection = Depends(get_tasks_col),
    users_col: AsyncIOMotorCollection = Depends(get_users_col)
):
    # Tasks stats
    total_tasks = await tasks_col.count_documents({})
    by_status = {}
    for status in TaskStatus:
        by_status[status.value] = await tasks_col.count_documents({"status": status.value})
    
    # Revenue calculation (sum of client_price for completed tasks)
    agg = tasks_col.aggregate([
        {"$match": {"status": TaskStatus.COMPLETED}},
        {"$group": {"_id": None, "sum": {"$sum": "$client_price"}}}
    ])
    total_revenue = 0
    async for x in agg:
        total_revenue = x.get("sum", 0)
    
    # Users stats
    total_users = await users_col.count_documents({})
    workers_count = await users_col.count_documents({"role": UserRole.WORKER})
    clients_count = await users_col.count_documents({"role": UserRole.CLIENT})
    
    return {
        "total_tasks": total_tasks,
        "by_status": by_status,
        "total_revenue": int(total_revenue),
        "total_users": total_users,
        "workers_count": workers_count,
        "clients_count": clients_count
    }

app.include_router(api)

# -----------------------------
# Frontend HTML Routes
# -----------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    try:
        # Get database collections
        tasks_col_instance = await get_tasks_col()
        users_col_instance = await get_users_col()
        stats = await stats_summary(tasks_col_instance, users_col_instance)
    except:
        stats = {}
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats
    })

@app.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request, status: Optional[str] = None):
    try:
        col = await get_tasks_col()
        tasks = await list_tasks(50, 0, status, None, None, col)
    except:
        tasks = []
    
    return templates.TemplateResponse("orders.html", {
        "request": request,
        "tasks": tasks,
        "current_filter": status
    })

@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, role: Optional[str] = None):
    try:
        col = await get_users_col()
        users = await list_users(50, 0, role, col)
    except:
        users = []
    
    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": users,
        "current_filter": role
    })

@app.get("/moderation", response_class=HTMLResponse)
async def moderation_page(request: Request):
    try:
        col = await get_tasks_col()
        tasks = await list_tasks(50, 0, "pending", None, None, col)
    except:
        tasks = []
    
    return templates.TemplateResponse("moderation.html", {
        "request": request,
        "tasks": tasks
    })

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    try:
        health_info = await health()
    except:
        health_info = None
    
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "health": health_info
    })

@app.get("/webapp", response_class=HTMLResponse)
async def webapp_page(request: Request, user_id: str = Query(...), tab: str = Query("tasks")):
    tasks = []
    reminders = []
    
    try:
        if tab == "tasks":
            col = await get_tasks_col()
            tasks = await list_tasks(50, 0, None, None, user_id, col)
        elif tab == "reminders":
            col = await get_reminders_col()
            reminders = await list_reminders(user_id, 50, col)
    except Exception as e:
        print(f"Error loading webapp data: {e}")
    
    return templates.TemplateResponse("webapp.html", {
        "request": request,
        "user_id": user_id,
        "active_tab": tab,
        "tasks": tasks,
        "reminders": reminders
    })

# -----------------------------
# Telegram Bot Handlers
# -----------------------------
MAIN_MENU, PROFILE, MY_TASKS, SEARCH, TASKS_VIEW, REMINDERS, SETTINGS = range(7)
CREATE_TASK, TASK_TITLE, TASK_DESC, TASK_TYPE, TASK_LOCATION, TASK_DATETIME, TASK_DURATION, TASK_REQUIREMENTS, TASK_PRICE = range(9, 18)

# Создаем основную клавиатуру
MAIN_KEYBOARD = [
    ["📋 Мои задания", "🔍 Поиск заданий"],
    ["➕ Создать задание", "👤 Профиль"],
    ["⏰ Напоминания", "💬 Поддержка"],
    ["⚙️ Настройки"]
]

WORKER_KEYBOARD = [
    ["📋 Доступные задания", "📝 Мои отклики"],  
    ["✅ Выполненные", "👤 Профиль"],
    ["⏰ Напоминания", "💬 Поддержка"],
    ["⚙️ Настройки"]
]

CLIENT_KEYBOARD = [
    ["➕ Создать задание", "📋 Мои задания"],
    ["👥 Нанятые", "👤 Профиль"], 
    ["📄 Документы", "💬 Поддержка"],
    ["⚙️ Настройки"]
]

# Функция для сохранения/обновления пользователя
async def save_user(update: Update, role: UserRole = UserRole.WORKER):
    global users_col
    if users_col is None:
        return
    
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    existing_user = await users_col.find_one({"tg_chat_id": chat_id})
    
    if existing_user:
        # Обновляем существующего пользователя
        await users_col.update_one(
            {"tg_chat_id": chat_id},
            {"$set": {
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name
            }}
        )
        return existing_user["id"]
    else:
        # Создаем нового пользователя
        user_id = uuid.uuid4().hex
        user_doc = {
            "id": user_id,
            "tg_chat_id": chat_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": None,
            "role": role,
            "is_active": True,
            "is_verified": False,
            "worker_profile": WorkerProfile().dict() if role == UserRole.WORKER else None,
            "client_profile": ClientProfile().dict() if role == UserRole.CLIENT else None,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await users_col.insert_one(user_doc)
        return user_id

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await save_user(update)
    
    # Создаем WebApp кнопку
    webapp_url = f"http://localhost:3000/webapp?user_id={user_id}"
    webapp_button = InlineKeyboardButton(
        "🌐 Открыть WebApp", 
        web_app=WebAppInfo(url=webapp_url)
    )
    
    welcome_text = (
        "🏢 Добро пожаловать в систему поиска работы!\n\n"
        "Здесь вы можете:\n"
        "• Найти работу (грузчик, водитель, такелажник)\n"
        "• Создать задание для исполнителей\n"
        "• Управлять своим профилем\n\n"
        "Выберите действие из меню или откройте WebApp:"
    )
    
    # Клавиатура с WebApp
    keyboard = InlineKeyboardMarkup([[webapp_button]])
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=keyboard
    )
    
    # Также отправляем обычную клавиатуру
    await update.message.reply_text(
        "Основное меню:",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
    )
    return MAIN_MENU

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "📋 Мои задания":
        return await show_my_tasks(update, context)
    elif text == "🔍 Поиск заданий":
        return await show_search_tasks(update, context)
    elif text == "➕ Создать задание":
        return await start_create_task(update, context)
    elif text == "👤 Профиль":
        return await show_profile(update, context)
    elif text == "⏰ Напоминания":
        return await show_reminders(update, context)
    elif text == "💬 Поддержка":
        return await show_support(update, context)
    elif text == "⚙️ Настройки":
        return await show_settings(update, context)
    else:
        await update.message.reply_text(
            "Пожалуйста, выберите действие из меню:",
            reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
        )
        return MAIN_MENU

async def show_my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if tasks_col is None:
        await update.message.reply_text("❌ База данных недоступна")
        return MAIN_MENU
    
    # Получаем задания пользователя
    user = await users_col.find_one({"tg_chat_id": chat_id}) if users_col else None
    if not user:
        await update.message.reply_text("❌ Пользователь не найден")
        return MAIN_MENU
    
    if user["role"] == UserRole.CLIENT:
        cursor = tasks_col.find({"client_id": user["id"]}).sort("created_at", -1).limit(10)
    else:
        # Для исполнителей показываем задания, где они участвуют
        cursor = tasks_col.find({"assigned_workers": user["id"]}).sort("created_at", -1).limit(10)
    
    tasks = []
    async for doc in cursor:
        tasks.append(doc)
    
    if not tasks:
        tasks_text = "📋 **Мои задания**\n\nУ вас пока нет заданий."
    else:
        tasks_text = f"📋 **Мои задания** (последние {len(tasks)})\n\n"
        
        for task in tasks:
            status_emoji = {
                TaskStatus.DRAFT: "📝",
                TaskStatus.PENDING: "⏳", 
                TaskStatus.APPROVED: "✅",
                TaskStatus.PUBLISHED: "📢",
                TaskStatus.IN_PROGRESS: "🔄",
                TaskStatus.COMPLETED: "✅",
                TaskStatus.CANCELLED: "❌",
                TaskStatus.URGENT: "🚨"
            }.get(TaskStatus(task.get("status", TaskStatus.DRAFT)), "❓")
            
            tasks_text += f"{status_emoji} **{task['title']}**\n"
            tasks_text += f"📍 {task.get('location', 'Не указано')}\n"
            tasks_text += f"💰 {task.get('client_price', 0)} ₽\n"
            tasks_text += f"📅 {task.get('start_datetime', '')[:16]}\n\n"
    
    back_keyboard = [["◀️ Главное меню"]]
    
    await update.message.reply_text(
        tasks_text,
        reply_markup=ReplyKeyboardMarkup(back_keyboard, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return MAIN_MENU

async def show_search_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if tasks_col is None:
        await update.message.reply_text("❌ База данных недоступна")
        return MAIN_MENU
    
    # Показываем доступные задания
    cursor = tasks_col.find({"status": TaskStatus.PUBLISHED}).sort("created_at", -1).limit(10)
    tasks = []
    async for doc in cursor:
        tasks.append(doc)
    
    if not tasks:
        search_text = "🔍 **Поиск заданий**\n\nДоступных заданий пока нет."
    else:
        search_text = f"🔍 **Доступные задания** ({len(tasks)})\n\n"
        
        for task in tasks:
            req_text = []
            for req in task.get("requirements", []):
                req_text.append(f"{req['count']} {req['worker_type']}")
            
            search_text += f"📋 **{task['title']}**\n"
            search_text += f"👥 Нужно: {', '.join(req_text)}\n"
            search_text += f"📍 {task.get('location', 'Не указано')}\n"
            search_text += f"💰 {task.get('worker_price', task.get('client_price', 0))} ₽\n"
            search_text += f"📅 {task.get('start_datetime', '')[:16]}\n\n"
    
    back_keyboard = [["◀️ Главное меню"]]
    
    await update.message.reply_text(
        search_text,
        reply_markup=ReplyKeyboardMarkup(back_keyboard, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return MAIN_MENU

async def show_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if reminders_col is None or users_col is None:
        await update.message.reply_text("❌ База данных недоступна")
        return MAIN_MENU
    
    # Получаем пользователя
    user = await users_col.find_one({"tg_chat_id": chat_id})
    if not user:
        await update.message.reply_text("❌ Пользователь не найден")
        return MAIN_MENU
    
    # Получаем напоминания пользователя из РЕАЛЬНОЙ базы данных
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    
    # Сегодняшние напоминания
    today_cursor = reminders_col.find({
        "user_id": user["id"],
        "remind_at": {"$gte": today_start.isoformat(), "$lt": tomorrow_start.isoformat()},
        "is_sent": False
    }).sort("remind_at", 1)
    
    # Завтрашние напоминания  
    tomorrow_end = tomorrow_start + timedelta(days=1)
    tomorrow_cursor = reminders_col.find({
        "user_id": user["id"],
        "remind_at": {"$gte": tomorrow_start.isoformat(), "$lt": tomorrow_end.isoformat()},
        "is_sent": False
    }).sort("remind_at", 1)
    
    today_reminders = []
    tomorrow_reminders = []
    
    async for doc in today_cursor:
        today_reminders.append(doc)
    async for doc in tomorrow_cursor:
        tomorrow_reminders.append(doc)
    
    reminders_text = "⏰ **Напоминания**\n\n"
    
    if today_reminders:
        reminders_text += "📅 **Сегодня:**\n"
        for reminder in today_reminders:
            time_str = datetime.fromisoformat(reminder["remind_at"]).strftime("%H:%M")
            reminders_text += f"• {time_str} - {reminder['title']}\n"
        reminders_text += "\n"
    
    if tomorrow_reminders:
        reminders_text += "📅 **Завтра:**\n"
        for reminder in tomorrow_reminders:
            time_str = datetime.fromisoformat(reminder["remind_at"]).strftime("%H:%M")
            reminders_text += f"• {time_str} - {reminder['title']}\n"
        reminders_text += "\n"
    
    if not today_reminders and not tomorrow_reminders:
        reminders_text += "У вас нет активных напоминаний.\n\n"
    
    reminders_text += "⚙️ Настройка напоминаний доступна в разделе 'Настройки'"
    
    back_keyboard = [["◀️ Главное меню"]]
    
    await update.message.reply_text(
        reminders_text,
        reply_markup=ReplyKeyboardMarkup(back_keyboard, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return MAIN_MENU

async def start_create_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "➕ **Создание задания**\n\n"
        "Для создания задания используйте веб-интерфейс - там удобнее заполнять все поля.\n\n"
        "Нажмите кнопку 'Открыть WebApp' в главном меню.",
        parse_mode="Markdown"
    )
    return MAIN_MENU

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Реализация профиля
    await update.message.reply_text("👤 Профиль - в разработке")
    return MAIN_MENU

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    support_text = (
        "💬 **Поддержка**\n\n"
        "Если у вас есть вопросы или проблемы, обратитесь к администратору.\n\n"
        "📞 Контакты поддержки будут добавлены позднее."
    )
    
    back_keyboard = [["◀️ Главное меню"]]
    
    await update.message.reply_text(
        support_text,
        reply_markup=ReplyKeyboardMarkup(back_keyboard, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return MAIN_MENU

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings_text = (
        "⚙️ **Настройки**\n\n"
        "🔔 Уведомления: ✅ Включены\n"
        "🌍 Язык: Русский\n"
        "⏰ Часовой пояс: MSK (UTC+3)\n\n"
        "Для изменения настроек используйте веб-интерфейс."
    )
    
    back_keyboard = [["◀️ Главное меню"]]
    
    await update.message.reply_text(
        settings_text,
        reply_markup=ReplyKeyboardMarkup(back_keyboard, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return MAIN_MENU

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выберите действие из меню:",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
    )
    return MAIN_MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Диалог завершён.",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
    )
    return MAIN_MENU

# Функция для уведомления заказчика о модерации
async def notify_client_about_moderation(task_data):
    """Уведомляет заказчика о результатах модерации задания"""
    global telegram_app, users_col
    
    if not telegram_app or not users_col:
        print("[notify] Telegram app or users collection not available")
        return
    
    try:
        # Находим заказчика
        client = await users_col.find_one({"id": task_data["client_id"]})
        if not client:
            print(f"[notify] Client not found: {task_data['client_id']}")
            return
        
        chat_id = client["tg_chat_id"]
        
        # Формируем сообщение
        if task_data["status"] == TaskStatus.APPROVED:
            message = (
                f"✅ **Ваше задание прошло модерацию!**\n\n"
                f"📋 **{task_data['title']}**\n"
                f"📍 {task_data['location']}\n"
                f"📅 {datetime.fromisoformat(task_data['start_datetime']).strftime('%d.%m.%Y %H:%M')}\n"
                f"💰 Стоимость: {task_data['client_price']} ₽\n\n"
            )
            
            if task_data.get("moderation_notes"):
                message += f"💬 Комментарий: {task_data['moderation_notes']}\n\n"
            
            message += "Задание будет опубликовано для исполнителей. Согласны с условиями?"
            
            # Кнопки согласия
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Да, согласен", callback_data=f"approve_task_{task_data['id']}")],
                [InlineKeyboardButton("❌ Нет, отменить", callback_data=f"reject_task_{task_data['id']}")]
            ])
            
            await telegram_app.bot.send_message(
                chat_id=chat_id,
                text=message,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
        elif task_data["status"] == TaskStatus.CANCELLED:
            message = (
                f"❌ **Ваше задание отклонено модератором**\n\n"
                f"📋 **{task_data['title']}**\n"
                f"📍 {task_data['location']}\n\n"
            )
            
            if task_data.get("moderation_notes"):
                message += f"💬 Причина: {task_data['moderation_notes']}\n\n"
            
            message += "Вы можете создать новое задание с учетом комментариев."
            
            await telegram_app.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown"
            )
            
        print(f"[notify] Notification sent to client {chat_id}")
        
    except Exception as e:
        print(f"[notify] Error sending notification: {e}")

# Обработчик кнопок согласия/отказа
async def handle_task_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ответ заказчика на модерацию"""
    global tasks_col
    
    query = update.callback_query
    await query.answer()
    
    data = query.data
    task_id = data.split("_")[-1]
    action = data.split("_")[0]
    
    if not tasks_col:
        await query.edit_message_text("❌ База данных недоступна")
        return
    
    try:
        task = await tasks_col.find_one({"id": task_id})
        if not task:
            await query.edit_message_text("❌ Задание не найдено")
            return
        
        if action == "approve":
            # Заказчик согласился - публикуем задание
            await tasks_col.update_one(
                {"id": task_id},
                {"$set": {
                    "status": TaskStatus.PUBLISHED,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            await query.edit_message_text(
                f"✅ **Задание опубликовано!**\n\n"
                f"📋 {task['title']}\n"
                f"Задание размещено для исполнителей. "
                f"Вы получите уведомление когда найдутся кандидаты.",
                parse_mode="Markdown"
            )
            
            # TODO: Уведомить исполнителей о новом задании
            
        elif action == "reject":
            # Заказчик отказался - отменяем задание
            await tasks_col.update_one(
                {"id": task_id},
                {"$set": {
                    "status": TaskStatus.CANCELLED,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            await query.edit_message_text(
                f"❌ **Задание отменено**\n\n"
                f"📋 {task['title']}\n"
                f"Задание удалено из системы.",
                parse_mode="Markdown"
            )
            
    except Exception as e:
        print(f"[approval] Error handling task approval: {e}")
        await query.edit_message_text("❌ Произошла ошибка при обработке ответа")

# -----------------------------
from contextlib import asynccontextmanager
from fastapi import FastAPI
from telegram.ext import Application
from motor.motor_asyncio import AsyncIOMotorClient

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler for FastAPI with proper startup/shutdown logic"""
    
    # Startup logic
    print("[startup] Initializing application...")
    
    # Init Mongo
    global mongo_client, db, users_col, tasks_col, applications_col, reminders_col, chats_col, payments_col, TELEGRAM_BOT_TOKEN
    if not MONGO_URL:
        print("[startup] MONGO_URL is not set. Database features will be unavailable.")
    else:
        mongo_client = AsyncIOMotorClient(MONGO_URL)
        db = mongo_client[DB_NAME]
        users_col = db[COLLECTION_USERS]
        tasks_col = db[COLLECTION_TASKS]
        applications_col = db[COLLECTION_APPLICATIONS]
        reminders_col = db[COLLECTION_REMINDERS]
        chats_col = db[COLLECTION_CHATS]
        payments_col = db[COLLECTION_PAYMENTS]
        
        try:
            # Create indexes
            await users_col.create_index("id", unique=True)
            await users_col.create_index("tg_chat_id", unique=True)
            await users_col.create_index([("created_at", -1)])
            
            await tasks_col.create_index("id", unique=True)
            await tasks_col.create_index("client_id")
            await tasks_col.create_index("status")
            await tasks_col.create_index([("created_at", -1)])
            
            await reminders_col.create_index("id", unique=True)
            await reminders_col.create_index("user_id")
            await reminders_col.create_index("remind_at")
            
        except Exception as e:
            print(f"[startup] Index error: {e}")

    # Init Telegram bot
    global telegram_app
    if TELEGRAM_BOT_TOKEN:
        try:
            print("[startup] Initializing Telegram bot...")
            
            telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

            conv = ConversationHandler(
                entry_points=[CommandHandler("start", cmd_start)],
                states={
                    MAIN_MENU: [MessageHandler(filters.TEXT & (~filters.COMMAND), main_menu_handler)],
                },
                fallbacks=[
                    CommandHandler("cancel", cancel),
                    MessageHandler(filters.Regex("^◀️ Главное меню$"), back_to_main)
                ],
            )
            telegram_app.add_handler(conv)
            telegram_app.add_handler(CommandHandler("cancel", cancel))

            await telegram_app.initialize()
            await telegram_app.start()
            
            # Polling with retry logic
            max_retries = 3
            retry_delay = 2
            
            for attempt in range(max_retries):
                try:
                    print(f"[startup] Starting Telegram bot polling (attempt {attempt + 1}/{max_retries})...")
                    await telegram_app.bot.delete_webhook(drop_pending_updates=True)
                    
                    await telegram_app.updater.start_polling(
                        allowed_updates=Update.ALL_TYPES,
                        drop_pending_updates=True,
                        read_timeout=30,
                        connect_timeout=30
                    )
                    print("[startup] Telegram bot polling started successfully")
                    break
                    
                except Exception as polling_error:
                    error_msg = str(polling_error)
                    if "Conflict" in error_msg or "terminated by other getUpdates request" in error_msg:
                        print(f"[startup] Telegram polling conflict detected (attempt {attempt + 1}): {error_msg}")
                        if attempt < max_retries - 1:
                            print(f"[startup] Waiting {retry_delay} seconds before retry...")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                            try:
                                await telegram_app.bot.delete_webhook(drop_pending_updates=True)
                                await asyncio.sleep(1)
                            except:
                                pass
                        else:
                            print("[startup] Max retries reached for Telegram bot polling.")
                    else:
                        print(f"[startup] Unexpected Telegram bot error: {polling_error}")
                        break
                        
        except Exception as e:
            print(f"[startup] Failed to initialize Telegram bot: {e}")
            telegram_app = None
    else:
        print("[startup] TELEGRAM_BOT_TOKEN is not set. Bot will not start.")

    yield  # App runs here
    
    # Shutdown logic
    print("[shutdown] Shutting down application...")
    
    # Stop Telegram bot
    if telegram_app is not None:
        try:
            print("[shutdown] Stopping Telegram bot...")
            if telegram_app.updater.running:
                await telegram_app.updater.stop()
            await telegram_app.stop()
            print("[shutdown] Telegram bot stopped successfully")
        except Exception as e:
            print(f"[shutdown] Error stopping telegram app: {e}")

    # Close MongoDB connection
    if mongo_client is not None:
        try:
            mongo_client.close()
            print("[shutdown] MongoDB connection closed")
        except Exception as e:
            print(f"[shutdown] Error closing MongoDB connection: {e}")

# Create FastAPI app with lifespan
app = FastAPI(lifespan=lifespan)