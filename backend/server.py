import os
import uuid
import asyncio
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import logging
import json

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

from fastapi import FastAPI, APIRouter, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from enum import Enum

# Telegram Bot (python-telegram-bot v21+)
from telegram import Update, ReplyKeyboardMarkup
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
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TOKEN")

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
TASKS_FILE = os.path.join(DATA_DIR, "tasks.json")
REMINDERS_FILE = os.path.join(DATA_DIR, "reminders.json")

# FastAPI app (только API для здоровья/ CRUD, без HTML)
app = FastAPI(title="Workers Telegram Bot Backend (No HTML)")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API router (all routes must be under /api)
api = APIRouter(prefix="/api")

# -----------------------------
# Simple JSON Storage (in place of DB)
# -----------------------------
class JsonStorage:
    def __init__(self, path: str):
        self.path = path
        self._lock = asyncio.Lock()
        self._data: Dict[str, Dict[str, Any]] = {}

    async def load(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            await self._save_internal()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                if isinstance(raw, dict):
                    self._data = raw
                else:
                    self._data = {}
        except Exception as e:
            logger.error(f"Failed to load {self.path}: {e}")
            self._data = {}

    async def _save_internal(self):
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.path)

    async def save(self):
        async with self._lock:
            await self._save_internal()

    async def upsert(self, doc_id: str, doc: Dict[str, Any]):
        async with self._lock:
            self._data[doc_id] = doc
            await self._save_internal()

    async def get(self, doc_id: str) -> Optional[Dict[str, Any]]:
        return self._data.get(doc_id)

    async def delete(self, doc_id: str):
        async with self._lock:
            if doc_id in self._data:
                del self._data[doc_id]
                await self._save_internal()

    async def find_many(self, filter_fn=None) -> List[Dict[str, Any]]:
        if filter_fn is None:
            return list(self._data.values())
        return [d for d in self._data.values() if filter_fn(d)]

    async def count(self, filter_fn=None) -> int:
        if filter_fn is None:
            return len(self._data)
        return len(await self.find_many(filter_fn))

# Global storages
users_store = JsonStorage(USERS_FILE)
tasks_store = JsonStorage(TASKS_FILE)
reminders_store = JsonStorage(REMINDERS_FILE)

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
# Helpers around storage
# -----------------------------
async def storage_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "using": "json",
        "files": {
            "users": os.path.exists(USERS_FILE),
            "tasks": os.path.exists(TASKS_FILE),
            "reminders": os.path.exists(REMINDERS_FILE),
        },
    }

async def user_by_tg_chat(chat_id: int) -> Optional[Dict[str, Any]]:
    users = await users_store.find_many(lambda u: u.get("tg_chat_id") == chat_id)
    return users[0] if users else None

# -----------------------------
# API Routes (/api)
# -----------------------------
@api.get("/health")
async def health():
    st = await storage_health()
    return {
        "ok": True,
        "service": "backend",
        "db_connected": False,
        "storage": st,
        "time": datetime.now(timezone.utc).isoformat(),
    }

@api.get("/users", response_model=List[UserOut])
async def list_users_api(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), role: Optional[UserRole] = None):
    users = await users_store.find_many(lambda u: (role is None) or (u.get("role") == role))
    users_sorted = sorted(users, key=lambda x: x.get("created_at", ""), reverse=True)
    sliced = users_sorted[offset: offset + limit]
    return [UserOut(**u) for u in sliced]

@api.post("/tasks", response_model=TaskOut)
async def create_task_api(payload: TaskCreate):
    task_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
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
        "created_at": now,
        "updated_at": now,
    }
    await tasks_store.upsert(task_id, doc)
    return TaskOut(**doc)

@api.get("/tasks", response_model=List[TaskOut])
async def list_tasks_api(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), status: Optional[TaskStatus] = None, task_type: Optional[TaskType] = None, client_id: Optional[str] = None):
    def filt(t: Dict[str, Any]):
        if status and t.get("status") != status:
            return False
        if task_type and t.get("task_type") != task_type:
            return False
        if client_id and t.get("client_id") != client_id:
            return False
        return True
    tasks = await tasks_store.find_many(filt)
    tasks_sorted = sorted(tasks, key=lambda x: x.get("created_at", ""), reverse=True)
    sliced = tasks_sorted[offset: offset + limit]
    return [TaskOut(**t) for t in sliced]

@api.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task_api(task_id: str):
    doc = await tasks_store.get(task_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskOut(**doc)

@api.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task_api(task_id: str, payload: TaskUpdate):
    current = await tasks_store.get(task_id)
    if not current:
        raise HTTPException(status_code=404, detail="Task not found")
    update_fields = {k: v for k, v in payload.dict().items() if v is not None}
    if update_fields:
        current.update(update_fields)
        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        await tasks_store.upsert(task_id, current)
    return TaskOut(**current)

@api.post("/reminders", response_model=ReminderOut)
async def create_reminder_api(payload: ReminderCreate):
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
    await reminders_store.upsert(reminder_id, doc)
    return ReminderOut(**doc)

@api.get("/reminders", response_model=List[ReminderOut])
async def list_reminders_api(user_id: Optional[str] = None, limit: int = Query(50, ge=1, le=200)):
    def filt(r: Dict[str, Any]):
        if user_id and r.get("user_id") != user_id:
            return False
        return True
    rems = await reminders_store.find_many(filt)
    rems_sorted = sorted(rems, key=lambda x: x.get("remind_at", ""))
    return [ReminderOut(**r) for r in rems_sorted[:limit]]

@api.get("/stats/summary")
async def stats_summary():
    try:
        all_tasks = await tasks_store.find_many()
        total_tasks = len(all_tasks)
        by_status: Dict[str, int] = {}
        for s in TaskStatus:
            by_status[s.value] = len([t for t in all_tasks if t.get("status") == s])
        total_revenue = int(sum([t.get("client_price", 0) for t in all_tasks if t.get("status") == TaskStatus.COMPLETED]))
        all_users = await users_store.find_many()
        total_users = len(all_users)
        workers_count = len([u for u in all_users if u.get("role") == UserRole.WORKER])
        clients_count = len([u for u in all_users if u.get("role") == UserRole.CLIENT])
        return {
            "total_tasks": total_tasks,
            "by_status": by_status,
            "total_revenue": total_revenue,
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
# Telegram Bot Handlers (Start, Profile, Create Task Conversation)
# -----------------------------
MAIN_MENU, TASK_TITLE, TASK_DESC, TASK_LOCATION, TASK_DATETIME, TASK_DURATION, TASK_PRICE = range(7)

MAIN_KEYBOARD = [
    ["📋 Мои задания", "🔍 Поиск заданий"],
    ["➕ Создать задание", "👤 Профиль"],
    ["⏰ Напоминания", "⚙️ Настройки"],
]

async def ensure_user(update: Update, default_role: UserRole = UserRole.WORKER) -> Optional[str]:
    user = update.effective_user
    chat_id = update.effective_chat.id
    existing = await user_by_tg_chat(chat_id)
    if existing:
        existing.update({
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
        })
        await users_store.upsert(existing["id"], existing)
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
    await users_store.upsert(new_id, doc)
    return new_id

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user(update)
    await update.message.reply_text(
        "🏢 Добро пожаловать в систему Рабочие! Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True),
    )
    return MAIN_MENU

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = await user_by_tg_chat(chat_id)
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
    text = (update.message.text or "").strip()
    low = text.lower()
    if text == "👤 Профиль" or "профиль" in low:
        return await show_profile(update, context)
    if text == "➕ Создать задание" or "создать" in low:
        context.user_data.clear()
        await update.message.reply_text("Введите название задания:")
        return TASK_TITLE
    if text == "📋 Мои задания" or "мои задания" in low:
        user = await user_by_tg_chat(update.effective_chat.id)
        if not user:
            await update.message.reply_text("❌ Пользователь не найден")
            return MAIN_MENU
        def filt(t: Dict[str, Any]):
            if user["role"] == "client":
                return t.get("client_id") == user["id"]
            return user["id"] in t.get("assigned_workers", [])
        tasks = await tasks_store.find_many(filt)
        tasks_sorted = sorted(tasks, key=lambda x: x.get("created_at", ""), reverse=True)[:10]
        if not tasks_sorted:
            await update.message.reply_text("У вас пока нет заданий")
            return MAIN_MENU
        msg = "📋 Мои задания\n\n"
        for t in tasks_sorted:
            msg += f"• {t['title']} — {t.get('status', 'draft')} — {t.get('client_price', 0)}₽\n"
        await update.message.reply_text(msg)
        return MAIN_MENU
    if low in {"start", "/start"}:
        return await cmd_start(update, context)
    await update.message.reply_text(
        "Выберите действие из меню ниже",
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
        from datetime import datetime as _dt
        dt = _dt.strptime(text, "%Y-%m-%d %H:%M")
        context.user_data["start_datetime"] = dt.replace(tzinfo=timezone.utc).isoformat()
    except Exception:
        await update.message.reply_text("Неверный формат. Пример: 2025-03-01 09:00")
        return TASK_DATETIME
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

    user = await user_by_tg_chat(update.effective_chat.id)
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
        await create_task_api(TaskCreate(**payload))  # type: ignore
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
telegram_app: Optional[Application] = None

@app.on_event("startup")
async def on_startup():
    global telegram_app
    await users_store.load()
    await tasks_store.load()
    await reminders_store.load()
    logger.info("✅ JSON storage initialized (No HTML mode)")

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
            logger.info("🤖 Telegram bot initialized (polling, no HTML)")
        except Exception as e:
            logger.error(f"Telegram bot init failed: {e}")

@app.on_event("shutdown")
async def on_shutdown():
    global telegram_app
    if telegram_app is not None:
        try:
            await telegram_app.stop()
            logger.info("🤖 Telegram bot stopped")
        except Exception as e:
            logger.error(f"Error stopping telegram app: {e}")