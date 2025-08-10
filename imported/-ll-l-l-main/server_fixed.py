import os
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

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
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import (Application, CommandHandler, MessageHandler, ConversationHandler,
                          ContextTypes, filters, CallbackQueryHandler)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# Enums and Constants
# -----------------------------
class UserRole(str, Enum):
    CLIENT = "client"
    WORKER = "worker"
    ADMIN = "admin"
    MODERATOR = "moderator"

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
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DB_NAME = os.environ.get("DB_NAME", "workersystem")

COLLECTION_USERS = "users"
COLLECTION_TASKS = "tasks"
COLLECTION_APPLICATIONS = "applications"
COLLECTION_REMINDERS = "reminders"
COLLECTION_CHATS = "chats"
COLLECTION_PAYMENTS = "payments"

app = FastAPI(title="Workers System - Full Stack Python")

# Templates and static files setup
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Template filters
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

# API router
api = APIRouter(prefix="/api")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Globals
mongo_client: Optional[AsyncIOMotorClient] = None
db: Optional[AsyncIOMotorDatabase] = None
users_col: Optional[AsyncIOMotorCollection] = None
tasks_col: Optional[AsyncIOMotorCollection] = None
applications_col: Optional[AsyncIOMotorCollection] = None
reminders_col: Optional[AsyncIOMotorCollection] = None
chats_col: Optional[AsyncIOMotorCollection] = None
payments_col: Optional[AsyncIOMotorCollection] = None
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

class TaskCreate(BaseModel):
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
    client_id: str

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
# Database Dependencies
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
# API Endpoints
# -----------------------------
@api.get("/health")
async def health():
    db_connected = False
    bot_status = "disabled"
    
    try:
        if db is not None:
            await db.command("ping")
            db_connected = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
    
    if telegram_app:
        bot_status = "enabled"
    
    return {
        "ok": True,
        "service": "workers-system",
        "db_connected": db_connected,
        "bot_status": bot_status,
        "time": datetime.now(timezone.utc).isoformat()
    }

# Users API
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

# Tasks API
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
    col: AsyncIOMotorCollection = Depends(get_tasks_col),
):
    filter_query = {}
    if status:
        filter_query["status"] = status
    
    cursor = col.find(filter_query).sort("created_at", -1).skip(offset).limit(limit)
    results: List[TaskOut] = []
    async for doc in cursor:
        results.append(TaskOut(**doc))
    return results

@api.get("/stats/summary")
async def stats_summary():
    try:
        if not tasks_col or not users_col:
            # Возвращаем демо данные если БД недоступна
            return {
                "total_tasks": 8,
                "by_status": {
                    "draft": 1,
                    "pending": 2,
                    "published": 3,
                    "completed": 2
                },
                "total_revenue": 45000,
                "total_users": 15,
                "workers_count": 10,
                "clients_count": 5
            }
        
        # Реальная статистика
        total_tasks = await tasks_col.count_documents({})
        by_status = {}
        for status in TaskStatus:
            by_status[status.value] = await tasks_col.count_documents({"status": status.value})
        
        # Revenue
        agg = tasks_col.aggregate([
            {"$match": {"status": TaskStatus.COMPLETED}},
            {"$group": {"_id": None, "sum": {"$sum": "$client_price"}}}
        ])
        total_revenue = 0
        async for x in agg:
            total_revenue = x.get("sum", 0)
        
        # Users
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
    except Exception as e:
        logger.error(f"Stats error: {e}")
        # Fallback to demo data
        return {
            "total_tasks": 5,
            "by_status": {"pending": 2, "published": 1, "completed": 2},
            "total_revenue": 25000,
            "total_users": 12,
            "workers_count": 8,
            "clients_count": 4
        }

app.include_router(api)

# -----------------------------
# Frontend Routes
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    try:
        stats = await stats_summary()
    except:
        stats = {
            "total_tasks": 0,
            "total_revenue": 0,
            "total_users": 0,
            "workers_count": 0,
            "by_status": {}
        }
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats
    })

@app.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request, status: Optional[str] = None):
    try:
        col = await get_tasks_col()
        tasks = await list_tasks(50, 0, status, col)
    except:
        # Демо данные если БД недоступна
        tasks = [
            {
                "id": "demo1",
                "title": "Погрузка мебели",
                "location": "Москва, Красная площадь",
                "client_price": 5000,
                "status": "pending",
                "start_datetime": "2025-08-11T10:00:00",
                "duration_hours": 4
            }
        ]
    
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
        tasks = await list_tasks(50, 0, "pending", col)
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
        health_info = {"ok": False, "db_connected": False, "bot_status": "error"}
    
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "health": health_info
    })

# -----------------------------
# Telegram Bot Setup
# -----------------------------
MAIN_MENU = 0

MAIN_KEYBOARD = [
    ["📋 Мои задания", "🔍 Поиск заданий"],
    ["➕ Создать задание", "👤 Профиль"],
    ["⏰ Напоминания", "💬 Поддержка"],
    ["⚙️ Настройки"]
]

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not users_col:
        await update.message.reply_text("❌ База данных недоступна")
        return
    
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Сохранение пользователя
    user_id = uuid.uuid4().hex
    user_doc = {
        "id": user_id,
        "tg_chat_id": chat_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": None,
        "role": UserRole.WORKER,
        "is_active": True,
        "is_verified": False,
        "worker_profile": WorkerProfile().dict(),
        "client_profile": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        await users_col.replace_one({"tg_chat_id": chat_id}, user_doc, upsert=True)
    except Exception as e:
        logger.error(f"Failed to save user: {e}")
    
    webapp_url = f"http://localhost:8001/webapp?user_id={user_id}"
    webapp_button = InlineKeyboardButton("🌐 Открыть WebApp", web_app=WebAppInfo(url=webapp_url))
    
    welcome_text = (
        "🏢 Добро пожаловать в Workers System!\n\n"
        "Здесь вы можете:\n"
        "• Найти работу (грузчик, водитель, такелажник)\n"
        "• Создать задание для исполнителей\n"
        "• Управлять своим профилем\n\n"
        "Выберите действие:"
    )
    
    keyboard = InlineKeyboardMarkup([[webapp_button]])
    
    await update.message.reply_text(welcome_text, reply_markup=keyboard)
    await update.message.reply_text(
        "Основное меню:",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
    )
    return MAIN_MENU

# -----------------------------
# Startup & Shutdown
# -----------------------------
@app.on_event("startup")
async def on_startup():
    global mongo_client, db, users_col, tasks_col, applications_col, reminders_col, chats_col, payments_col, telegram_app
    
    # MongoDB setup
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
            
            # Test connection
            await db.command("ping")
            logger.info("✅ MongoDB connected successfully")
            
            # Create indexes
            await users_col.create_index("id", unique=True)
            await users_col.create_index("tg_chat_id", unique=True)
            await tasks_col.create_index("id", unique=True)
            
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            logger.info("🚀 Starting without database - using demo data")
    else:
        logger.info("📝 MONGO_URL not set - using demo data")
    
    # Telegram Bot setup
    if TELEGRAM_BOT_TOKEN:
        try:
            telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
            
            conv = ConversationHandler(
                entry_points=[CommandHandler("start", cmd_start)],
                states={MAIN_MENU: []},
                fallbacks=[]
            )
            telegram_app.add_handler(conv)
            
            await telegram_app.initialize()
            await telegram_app.start()
            await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            logger.info("🤖 Telegram bot started successfully")
            
        except Exception as e:
            logger.error(f"❌ Telegram bot failed to start: {e}")
            logger.info("🚀 Starting without Telegram bot")
    else:
        logger.info("📝 TELEGRAM_BOT_TOKEN not set - starting without bot")

@app.on_event("shutdown")
async def on_shutdown():
    if telegram_app:
        try:
            await telegram_app.stop()
            logger.info("🤖 Telegram bot stopped")
        except Exception as e:
            logger.error(f"Error stopping telegram bot: {e}")
    
    if mongo_client:
        mongo_client.close()
        logger.info("🗄️ MongoDB connection closed")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)