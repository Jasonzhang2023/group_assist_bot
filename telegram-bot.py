from config import *
from flask import Flask, request, jsonify, session, redirect, url_for, send_file, render_template
from datetime import timedelta
import httpx
import telegram
from telegram import Update
from telegram.request import HTTPXRequest
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime
import pytz
import sqlite3
from pathlib import Path
import asyncio
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from contextlib import asynccontextmanager
from telegram.error import NetworkError, Forbidden, BadRequest
from telegram.constants import ChatMemberStatus
from telegram import ChatPermissions
import threading
from concurrent.futures import ThreadPoolExecutor
import time
from telegram import ChatMember
import re

# 1. 首先创建 logger
logger = logging.getLogger('TelegramBot')

# 2. 创建日志处理器
handler = RotatingFileHandler(
    LOGGING['FILE_PATH'], 
    maxBytes=LOGGING['MAX_BYTES'], 
    backupCount=LOGGING['BACKUP_COUNT']
)

# 3. 创建格式化器
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# 4. 添加处理器到 logger
logger.addHandler(handler)

# 5. 设置日志级别
logger.setLevel(LOGGING['LEVEL'])

# 6. 基础目录配置
app = Flask(__name__,
    static_folder=STATIC['FOLDER'],
    static_url_path=STATIC['URL_PATH'])
app.secret_key = SERVER['SECRET_KEY']


ACCESS_TOKEN = SERVER['ACCESS_TOKEN']
DB_PATH = DATABASE['PATH']

CHINA_TZ = pytz.timezone(TIMEZONE)

# 确保目录存在
def init_directories():
    """初始化所需的所有目录"""
    directories = [
        BASE_DIR,
        LOG_DIR,
        DB_DIR,
        FILES_DIR
    ]
    
    for directory in directories:
        try:
            Path(directory).mkdir(exist_ok=True, parents=True)
            os.chmod(directory, 0o755)
        except Exception as e:
            print(f"Failed to create/check directory {directory}: {str(e)}")
            raise

# 先创建目录
init_directories()


# Bot 管理器类
class TelegramBotManager:
    def __init__(self):
        self.token = TELEGRAM['BOT_TOKEN']
        self._request = None
        self.bot = None
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self):
        """初始化 bot 管理器"""
        async with self._lock:
            if not self._initialized:
                try:
                    # 为每个新的事件循环创建新的请求对象
                    self._request = HTTPXRequest(
                        connection_pool_size=HTTP['CONNECTION_POOL_SIZE'],
                        connect_timeout=HTTP['CONNECT_TIMEOUT'],
                        read_timeout=HTTP['READ_TIMEOUT'],
                        write_timeout=HTTP['WRITE_TIMEOUT'],
                        pool_timeout=HTTP['POOL_TIMEOUT']
                    )
                    self.bot = telegram.Bot(token=self.token, request=self._request)
                    await self.bot.get_me()
                    self._initialized = True
                    logger.info("Bot connection pool warmed up successfully")
                except Exception as e:
                    logger.error(f"Failed to warm up bot connection pool: {e}")
                    raise

    @asynccontextmanager
    async def get_bot(self):
        """获取 bot 实例的上下文管理器"""
        try:
            # 确保在当前事件循环中初始化
            if not self._initialized:
                await self.initialize()
            # 为每次请求创建新的 bot 实例
            request = HTTPXRequest(
                connection_pool_size=1,
                connect_timeout=30.0,
                read_timeout=30.0,
                write_timeout=30.0,
                pool_timeout=3.0
            )
            bot = telegram.Bot(token=self.token, request=request)
            yield bot
        except Exception as e:
            logger.error(f"Error in bot operation: {e}")
            raise

# 创建全局 bot 管理器
bot_manager = TelegramBotManager()


class TaskManager:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=10)
        self._lock = threading.Lock()
        self._tasks = {}

    def schedule_task(self, task_id, func, delay):
        """调度一个延迟执行的任务"""
        def delayed_task():
            try:
                logger.info(f"[定时任务] 开始执行任务 {task_id}, 延迟 {delay} 秒")
                time.sleep(delay)
                
                # 检查任务是否被取消
                with self._lock:
                    if task_id not in self._tasks:
                        logger.info(f"[定时任务] 任务 {task_id} 已被取消，不执行")
                        return
                
                # 创建新的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # 创建新的 bot 实例
                    request = HTTPXRequest(
                        connection_pool_size=1,
                        connect_timeout=30.0,
                        read_timeout=30.0,
                        write_timeout=30.0,
                        pool_timeout=3.0
                    )
                    bot = telegram.Bot(token=TOKEN, request=request)
                    
                    # 执行异步操作
                    coroutine = func(bot)
                    result = loop.run_until_complete(coroutine)
                    logger.info(f"[定时任务] 任务 {task_id} 执行成功")
                    return result
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
                    
            except asyncio.CancelledError:
                logger.info(f"[定时任务] 任务 {task_id} 被取消")
            except Exception as e:
                logger.error(f"[定时任务] 任务 {task_id} 执行失败: {str(e)}", exc_info=True)
            finally:
                with self._lock:
                    self._tasks.pop(task_id, None)
                    logger.info(f"[定时任务] 任务 {task_id} 已从队列中移除")

        with self._lock:
            # 如果已存在相同ID的任务，先取消它
            if task_id in self._tasks:
                try:
                    self._tasks[task_id].cancel()
                    logger.info(f"[定时任务] 取消已存在的任务 {task_id}")
                except Exception as e:
                    logger.error(f"[定时任务] 取消任务 {task_id} 时出错: {str(e)}")
                self._tasks.pop(task_id, None)
            
            # 提交新任务
            future = self.executor.submit(delayed_task)
            self._tasks[task_id] = future
            logger.info(f"[定时任务] 已调度任务 {task_id}, 将在 {delay} 秒后执行")

# 创建全局任务管理器实例
task_manager = TaskManager()

def async_route(f):
    """异步路由装饰器"""
    @wraps(f)
    def wrapped(*args, **kwargs):
        loop = None
        try:
            # 尝试获取当前事件循环
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 如果没有运行中的循环，创建一个新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            return loop.run_until_complete(f(*args, **kwargs))
        finally:
            # 如果我们创建了新的循环，确保清理它
            if loop and not loop.is_running():
                loop.close()
    return wrapped

def init_db():
    """初始化数据库"""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 首先检查消息表
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
        messages_exists = c.fetchone() is not None
        
        # 检查自动禁言设置表
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='auto_mute_settings'")
        auto_mute_exists = c.fetchone() is not None
        
        # 检查入群验证设置表
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='join_settings'")
        join_settings_exists = c.fetchone() is not None
        
        # 检查待验证用户表
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pending_members'")
        pending_members_exists = c.fetchone() is not None

        # 检查垃圾信息过滤设置表
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='spam_filter_settings'")
        spam_filter_exists = c.fetchone() is not None
        
        # 添加这段新代码：检查白名单表
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='spam_filter_whitelist'")
        whitelist_exists = c.fetchone() is not None

        if not spam_filter_exists:
            c.execute('''
                CREATE TABLE spam_filter_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL UNIQUE,
                    enabled BOOLEAN DEFAULT 0,
                    rules TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            logger.info("Created spam_filter_settings table")

        # 创建必要的表
        if not messages_exists:
            c.execute('''
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    chat_id INTEGER NOT NULL,
                    chat_title TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    from_user_id INTEGER,
                    message_type TEXT NOT NULL,
                    message_content TEXT NOT NULL,
                    file_path TEXT,
                    chat_type TEXT NOT NULL,
                    is_topic_message BOOLEAN DEFAULT 0,
                    topic_id INTEGER,
                    forward_from TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            logger.info("Created new messages table")

        if not auto_mute_exists:
            c.execute('''
                CREATE TABLE auto_mute_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL UNIQUE,
                    enabled BOOLEAN DEFAULT 0,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    days_of_week TEXT NOT NULL,
                    mute_level TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            logger.info("Created new auto_mute_settings table")

        if not join_settings_exists:
            c.execute('''
                CREATE TABLE join_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL UNIQUE,
                    enabled BOOLEAN DEFAULT 0,
                    verify_type TEXT DEFAULT 'question',
                    question TEXT,
                    answer TEXT,
                    welcome_message TEXT,
                    timeout INTEGER DEFAULT 300,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            logger.info("Created join_settings table")
        
        if not pending_members_exists:
            c.execute('''
                CREATE TABLE pending_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    full_name TEXT,
                    join_time DATETIME NOT NULL,
                    verify_deadline DATETIME NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chat_id, user_id)
                )
            ''')
            logger.info("Created pending_members table")
        
        if not whitelist_exists:
            c.execute('''
                CREATE TABLE spam_filter_whitelist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    full_name TEXT,
                    added_by INTEGER NOT NULL,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    note TEXT,
                    UNIQUE(chat_id, user_id)
                )
            ''')
            logger.info("Created spam_filter_whitelist table")

        conn.commit()
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        logger.error("Error details:", exc_info=True)
        if conn:
            try:
                conn.rollback()
            except:
                pass
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

def save_message(message_data):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute("""
            INSERT INTO messages (
                timestamp, chat_id, chat_title, user_name, from_user_id,
                message_type, message_content, file_path, chat_type,
                is_topic_message, topic_id, forward_from
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            message_data['timestamp'],
            message_data['chat_id'],
            message_data['chat_title'],
            message_data['user_name'],
            message_data.get('from_user_id'),
            message_data['message_type'],
            message_data['message_content'],
            message_data.get('file_path'),
            message_data['chat_type'],
            message_data.get('is_topic_message', False),
            message_data.get('topic_id'),
            message_data.get('forward_from')
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"Message saved successfully: {message_data['message_type']}")
    except Exception as e:
        logger.error(f"Error saving message to database: {str(e)}")

async def download_file(file):
    """下载Telegram文件"""
    try:
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_ext = '.jpg'  # 默认扩展名
        
        # 获取文件信息并确定正确的扩展名
        async with bot_manager.get_bot() as bot:
            try:
                file_info = await bot.get_file(file.file_id)
                if not file_info or not file_info.file_path:
                    logger.error("Failed to get file info or file path is empty")
                    return None
                
                # 从完整URL中提取实际的文件路径
                actual_path = file_info.file_path
                if "https://" in actual_path:
                    # 提取实际的文件路径部分
                    actual_path = actual_path.split("/file/bot" + TELEGRAM['BOT_TOKEN'] + "/")[-1]
                
                file_ext = os.path.splitext(actual_path)[1] or '.jpg'
                logger.info(f"Got file info: {actual_path}")
            except Exception as e:
                logger.error(f"Error getting file info: {str(e)}")
                return None

        # 构建文件路径
        filename = f'{timestamp}_{file.file_unique_id}{file_ext}'
        file_path = os.path.join(FILES_DIR, filename)
        web_path = f'/serve_file/{filename}'
        
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # 构建下载URL，使用处理后的路径
        download_url = f"https://api.telegram.org/file/bot{TELEGRAM['BOT_TOKEN']}/{actual_path}"
        logger.info(f"Attempting to download from: {download_url}")
        
        timeout = httpx.Timeout(30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(download_url)
            
            if response.status_code == 200:
                # 写入文件
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                
                # 设置文件权限
                os.chmod(file_path, 0o644)
                logger.info(f"File downloaded successfully: {file_path}")
                
                return web_path
            else:
                logger.error(f"Failed to download file. Status: {response.status_code}, Response: {response.text}")
                return None
                
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}", exc_info=True)
        return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'authenticated' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function



@app.route('/auto_mute/delete', methods=['POST'])
@login_required
def delete_auto_mute_setting():
    """删除自动禁言设置"""
    print("=== 进入删除自动禁言设置路由 ===")  # 添加控制台打印
    logger.info("=== 进入删除自动禁言设置路由 ===")
    
    # 打印请求信息
    print(f"Request method: {request.method}")
    print(f"Request headers: {dict(request.headers)}")
    print(f"Request data: {request.get_data()}")
    
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        
        logger.info(f"收到删除请求，chat_id: {chat_id}")
        print(f"收到删除请求，chat_id: {chat_id}")
        
        if not chat_id:
            return jsonify({
                'status': 'error',
                'message': '缺少群组ID'
            }), 400
            
        try:
            chat_id = int(chat_id)
        except ValueError:
            return jsonify({
                'status': 'error',
                'message': '无效的ID格式'
            }), 400

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 先检查设置是否存在
        c.execute('SELECT COUNT(*) FROM auto_mute_settings WHERE chat_id = ?', (chat_id,))
        count = c.fetchone()[0]
        
        logger.info(f"找到 {count} 条匹配的设置")
        print(f"找到 {count} 条匹配的设置")
        
        if count == 0:
            return jsonify({
                'status': 'error',
                'message': '未找到该设置'
            }), 404
        
        # 删除设置
        c.execute('DELETE FROM auto_mute_settings WHERE chat_id = ?', (chat_id,))
        rows_affected = c.rowcount
        
        logger.info(f"删除影响的行数: {rows_affected}")
        print(f"删除影响的行数: {rows_affected}")
        
        conn.commit()
        
        return jsonify({
            'status': 'success',
            'message': '设置已删除'
        })

    except Exception as e:
        logger.error(f"删除设置时发生错误: {str(e)}", exc_info=True)
        print(f"删除设置时发生错误: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'删除失败: {str(e)}'
        }), 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/auto_mute/settings', methods=['POST'])
@login_required
@async_route
async def auto_mute_settings():
    """获取或更新自动禁言设置"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        data = request.get_json()
        chat_id = data.get('chat_id')
        enabled = data.get('enabled', False)
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        days_of_week = ','.join(map(str, data.get('days_of_week', [])))
        mute_level = data.get('mute_level')

        if not all([chat_id, start_time, end_time, mute_level]):
            return jsonify({'status': 'error', 'message': '缺少必要参数'}), 400

        # 获取当前北京时间
        now = datetime.now(CHINA_TZ)
        
        # 使用 UPSERT 语法更新或插入设置
        c.execute('''
            INSERT INTO auto_mute_settings 
            (chat_id, enabled, start_time, end_time, days_of_week, mute_level, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
            enabled=excluded.enabled,
            start_time=excluded.start_time,
            end_time=excluded.end_time,
            days_of_week=excluded.days_of_week,
            mute_level=excluded.mute_level,
            updated_at=excluded.updated_at
        ''', (chat_id, enabled, start_time, end_time, days_of_week, mute_level, now.strftime('%Y-%m-%d %H:%M:%S')))
        
        conn.commit()

        # 检查是否在设定时间范围内
        now = datetime.now(CHINA_TZ)
        current_time = now.time()
        current_day = now.weekday()
        
        if enabled:
            start = datetime.strptime(start_time, '%H:%M').time()
            end = datetime.strptime(end_time, '%H:%M').time()
            days = [int(d) for d in days_of_week.split(',')]
            
            def is_in_time_range(current, start, end):
                current_minutes = current.hour * 60 + current.minute
                start_minutes = start.hour * 60 + start.minute
                end_minutes = end.hour * 60 + end.minute
                
                if end_minutes < start_minutes:  # 跨日情况
                    return current_minutes >= start_minutes or current_minutes < end_minutes
                else:  # 同日情况
                    return start_minutes <= current_minutes < end_minutes

            # 如果是当前要禁言的时间，立即执行禁言
            if current_day in days and is_in_time_range(current_time, start, end):
                async with bot_manager.get_bot() as bot:
                    # 设置禁言权限
                    permissions = ChatPermissions(
                        can_send_messages=mute_level != 'strict',
                        can_send_polls=False,
                        can_send_other_messages=False,
                        can_add_web_page_previews=False,
                        can_change_info=False,
                        can_invite_users=False,
                        can_pin_messages=False
                    )
                    
                    await bot.set_chat_permissions(
                        chat_id=chat_id,
                        permissions=permissions
                    )
                    
                    # 发送开启通知，使用固定的时段格式
                    notification_text = (
                        "🌙 自动禁言模式已开始\n\n"
                        f"⏰ 禁言时段：{start_time} - {end_time}\n"
                        f"📅 生效日期：{formatDays(days)}\n"
                        f"🔒 禁言级别：{mute_level == 'strict' and '严格（禁止所有消息）' or '轻度（仅允许文字消息）'}\n\n"
                        "⚠️ 请各位成员注意休息"
                    )
                    await bot.send_message(
                        chat_id=chat_id,
                        text=notification_text,
                        parse_mode='HTML'
                    )
                    logger.info(f"[禁言] 群组 {chat_id} 被禁言并已发送通知")

        return jsonify({'status': 'success', 'message': '设置已更新'})

    except Exception as e:
        logger.error(f"Error in auto_mute_settings: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/webhook', methods=['POST'])
@async_route
async def webhook():
    try:
        logger.info("Webhook received a request")
        data = request.get_json()
        logger.info(f"Webhook raw data: {data}")

        update = Update.de_json(data, bot_manager.bot)
        logger.info(f"Update object created: {update}")
        
        if update.message:
            message = update.message
            chat_id = message.chat.id
            chat_type = message.chat.type
            
            logger.info(f"Processing message from chat {chat_id} of type {chat_type}")
            
            # 首先进行垃圾信息检测
            if chat_type in ['group', 'supergroup'] and (message.text or message.caption):
                logger.info(f"[消息处理] 开始检查是否为垃圾信息")
                is_spam, action = await check_spam(message, chat_id)
                if is_spam:
                    logger.info(f"[消息处理] 检测到垃圾信息，action={action}")
                    try:
                        async with bot_manager.get_bot() as bot:
                            # 根据不同动作执行不同操作
                            if action == 'delete':
                                # 仅在动作为delete时删除消息
                                await bot.delete_message(chat_id=chat_id, message_id=message.message_id)
                                logger.info(f"[消息处理] 已删除垃圾消息: chat_id={chat_id}, message_id={message.message_id}")
                            
                            if action == 'warn':
                                warning_text = f"⚠️ {message.from_user.mention_html()} 请不要发送垃圾信息"
                                await bot.send_message(
                                    chat_id=chat_id,
                                    text=warning_text,
                                    parse_mode='HTML'
                                )
                            elif action == 'mute':
                                # 删除消息并禁言
                                await bot.delete_message(chat_id=chat_id, message_id=message.message_id)
                                permissions = ChatPermissions(
                                    can_send_messages=False,
                                    can_send_polls=False,
                                    can_send_other_messages=False,
                                    can_add_web_page_previews=False
                                )
                                await bot.restrict_chat_member(
                                    chat_id=chat_id,
                                    user_id=message.from_user.id,
                                    permissions=permissions,
                                    until_date=datetime.now() + timedelta(minutes=10)
                                )
                                mute_text = f"🚫 {message.from_user.mention_html()} 因发送垃圾信息已被禁言10分钟"
                                await bot.send_message(
                                    chat_id=chat_id,
                                    text=mute_text,
                                    parse_mode='HTML'
                                )
                            return jsonify({'status': 'success'})
                    except Exception as e:
                        logger.error(f"Error handling spam message: {str(e)}")

            # 处理新成员加入
            if message.new_chat_members:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                
                try:
                    # 清理用户旧的验证记录
                    for new_member in message.new_chat_members:
                        if not new_member.is_bot:
                            c.execute('''
                                DELETE FROM pending_members 
                                WHERE chat_id = ? AND user_id = ?
                            ''', (chat_id, new_member.id))
                            conn.commit()
                            logger.info(f"Cleared old verification records for user {new_member.id}")

                    # 检查是否启用了入群验证
                    c.execute('''
                        SELECT enabled, verify_type, question, answer, 
                               welcome_message, timeout
                        FROM join_settings 
                        WHERE chat_id = ? AND enabled = 1
                    ''', (chat_id,))
                    
                    settings = c.fetchone()
                    logger.info(f"Verification settings for chat {chat_id}: {settings}")
                    
                    if settings:
                        enabled, verify_type, question, answer, welcome_msg, timeout = settings
                        
                        for new_member in message.new_chat_members:
                            if not new_member.is_bot:
                                # 记录待验证用户
                                join_time = datetime.now(CHINA_TZ)
                                verify_deadline = join_time + timedelta(seconds=timeout)
                                
                                try:
                                    c.execute('''
                                        INSERT INTO pending_members 
                                        (chat_id, user_id, username, full_name, 
                                         join_time, verify_deadline, status)
                                        VALUES (?, ?, ?, ?, ?, ?, ?)
                                    ''', (
                                        chat_id, new_member.id, new_member.username,
                                        new_member.full_name, join_time.strftime('%Y-%m-%d %H:%M:%S'),
                                        verify_deadline.strftime('%Y-%m-%d %H:%M:%S'), 'pending'
                                    ))
                                    conn.commit()
                                    logger.info(f"Added new pending verification for user {new_member.id}")
                                    
                                    # 限制新用户权限
                                    async with bot_manager.get_bot() as bot:
                                        permissions = ChatPermissions(
                                            can_send_messages=False,
                                            can_send_polls=False,
                                            can_send_other_messages=False,
                                            can_add_web_page_previews=False
                                        )
                                        await bot.restrict_chat_member(
                                            chat_id=chat_id,
                                            user_id=new_member.id,
                                            permissions=permissions
                                        )
                                        logger.info(f"Restricted permissions for user {new_member.id}")
                                        
                                        if verify_type == 'question':
                                            try:
                                                # 先在群里发送简单通知（自动删除）
                                                group_msg = (
                                                    f"👋 欢迎 {new_member.mention_html()}\n"
                                                    "验证消息已通过私聊发送，请查收。"
                                                )
                                                await send_auto_delete_message(
                                                    bot=bot,
                                                    chat_id=chat_id,
                                                    text=group_msg,
                                                    parse_mode='HTML'
                                                )
                                                
                                                # 通过私聊发送验证问题
                                                verify_msg = (
                                                    f"👋 您好！要加入群组，请先回答以下问题：\n\n"
                                                    f"❓ {question}\n\n"
                                                    f"⏰ 请在 {timeout} 秒内回复答案\n\n"
                                                    "⚠️ 注意：请直接回复答案，不需要附加其他内容"
                                                )
                                                await bot.send_message(
                                                    chat_id=new_member.id,
                                                    text=verify_msg
                                                )
                                                logger.info(f"Sent verification question to user {new_member.id}")
                                                
                                            except telegram.error.Forbidden:
                                                # 如果用户没有启用私聊，发送提醒
                                                warning_msg = (
                                                    f"{new_member.mention_html()}，由于您的隐私设置，机器人无法向您发送私聊消息。\n"
                                                    "请先点击 @your_bot_username 启用私聊，然后重新加入群组。"
                                                )
                                                await send_auto_delete_message(
                                                    bot=bot,
                                                    chat_id=chat_id,
                                                    text=warning_msg,
                                                    parse_mode='HTML'
                                                )
                                                # 移除用户
                                                await bot.ban_chat_member(chat_id=chat_id, user_id=new_member.id)
                                                await bot.unban_chat_member(chat_id=chat_id, user_id=new_member.id)
                                        else:
                                            # 管理员审核模式
                                            verify_msg = (
                                                f"👋 欢迎 {new_member.mention_html()}\n\n"
                                                "⌛️ 请等待管理员验证\n\n"
                                                f"⏰ 验证时限：{timeout} 秒"
                                            )
                                            await send_auto_delete_message(
                                                bot=bot,
                                                chat_id=chat_id,
                                                text=verify_msg,
                                                parse_mode='HTML'
                                            )
                                            logger.info(f"Set up admin verification for user {new_member.id}")
                                        
                                        # 创建超时任务
                                        task_id = f"verify_{chat_id}_{new_member.id}"
                                        task_manager.schedule_task(
                                            task_id,
                                            lambda bot: handle_verification_timeout(bot, chat_id, new_member.id),
                                            timeout
                                        )
                                        logger.info(f"Scheduled timeout task for user {new_member.id}")
                                
                                except sqlite3.IntegrityError as e:
                                    logger.error(f"Database error adding user {new_member.id}: {e}")
                finally:
                    conn.close()

            # 处理常规消息
            # 安全地获取用户信息
            user = message.from_user
            user_full_name = "未知用户"
            user_name = "unknown"
            user_id = None

            if user:
                user_full_name = user.full_name or f"{user.first_name or ''} {user.last_name or ''}".strip() or "未知用户"
                user_name = user.username or user_full_name
                user_id = user.id

            # 根据不同类型设置标题和用户名
            if chat_type == 'private':
                chat_title = f"与 {user_full_name} 的私聊"
            elif chat_type == 'channel':
                chat_title = message.chat.title or "未命名频道"
                user_name = message.author_signature or "频道管理员"
            elif chat_type in ['group', 'supergroup']:
                chat_title = message.chat.title or "未命名群组"
                if (hasattr(message, 'is_topic_message') and message.is_topic_message and 
                    hasattr(message, 'reply_to_message') and message.reply_to_message and 
                    hasattr(message, 'reply_to_message', 'forum_topic_created') and 
                    message.reply_to_message.forum_topic_created):
                    chat_title = f"{chat_title} (主题: {message.reply_to_message.forum_topic_created.name})"
            else:
                chat_title = message.chat.title or "未知类型聊天"
            
            logger.info(f"Message details: chat_title={chat_title}, user_name={user_name}")

            message_content = message.text or ''
            message_data = {
                'timestamp': datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S UTC'),
                'chat_id': chat_id,
                'chat_title': chat_title,
                'user_name': user_name,
                'from_user_id': user_id,
                'message_type': 'text',
                'message_content': '',
                'file_path': None,
                'chat_type': chat_type,
                'is_topic_message': getattr(message, 'is_topic_message', False),
                'topic_id': getattr(message, 'message_thread_id', None),
                'forward_from': None
            }

            # 处理转发消息
            if hasattr(message, 'forward_from') and message.forward_from:
                forward_name = (getattr(message.forward_from, 'full_name', None) or 
                              f"{getattr(message.forward_from, 'first_name', '')} {getattr(message.forward_from, 'last_name', '')}".strip() or 
                              "未知用户")
                message_data['forward_from'] = f"用户 {forward_name}"
            elif hasattr(message, 'forward_from_chat') and message.forward_from_chat:
                forward_chat = message.forward_from_chat
                forward_type = getattr(forward_chat, 'type', 'group')
                forward_title = getattr(forward_chat, 'title', '未知来源')
                message_data['forward_from'] = f"{'频道' if forward_type == 'channel' else '群组'} {forward_title}"

            # 处理不同类型的消息
            if hasattr(message, 'text') and message.text:
                message_data['message_type'] = 'text'
                message_data['message_content'] = message.text
                logger.info(f"Text message content: {message.text}")
            elif hasattr(message, 'photo') and message.photo:
                message_data['message_type'] = 'photo'
                message_data['message_content'] = getattr(message, 'caption', '') or ''
                message_data['file_path'] = await download_file(message.photo[-1])
                logger.info("Photo message processed")
            elif hasattr(message, 'video') and message.video:
                message_data['message_type'] = 'video'
                message_data['message_content'] = getattr(message, 'caption', '') or ''
                message_data['file_path'] = await download_file(message.video)
                logger.info("Video message processed")
            elif hasattr(message, 'document') and message.document:
                message_data['message_type'] = 'document'
                message_data['message_content'] = getattr(message, 'caption', '') or ''
                message_data['file_path'] = await download_file(message.document)
                logger.info("Document message processed")
            elif hasattr(message, 'sticker') and message.sticker:
                message_data['message_type'] = 'sticker'
                message_data['message_content'] = getattr(message.sticker, 'emoji', '') or ''
                message_data['file_path'] = await download_file(message.sticker)
                logger.info("Sticker message processed")
            
            logger.info(f"Final message_data: {message_data}")
            save_message(message_data)
            logger.info(f"Message saved to database")

        elif update.channel_post:
            # 处理频道消息
            message = update.channel_post
            chat_id = message.chat.id
            chat_type = message.chat.type
            chat_title = message.chat.title or "未命名频道"
            user_name = message.author_signature or "频道管理员"
            
            message_data = {
                'timestamp': datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S UTC'),
                'chat_id': chat_id,
                'chat_title': chat_title,
                'user_name': user_name,
                'from_user_id': None,
                'message_type': 'text',
                'message_content': '',
                'file_path': None,
                'chat_type': chat_type,
                'is_topic_message': False,
                'topic_id': None,
                'forward_from': None
            }
            
            # 处理不同类型的频道消息
            if hasattr(message, 'text') and message.text:
                message_data['message_type'] = 'text'
                message_data['message_content'] = message.text
                logger.info(f"Channel text message: {message.text}")
            elif hasattr(message, 'photo') and message.photo:
                message_data['message_type'] = 'photo'
                message_data['message_content'] = getattr(message, 'caption', '') or ''
                message_data['file_path'] = await download_file(message.photo[-1])
                logger.info("Channel photo message processed")
            elif hasattr(message, 'video') and message.video:
                message_data['message_type'] = 'video'
                message_data['message_content'] = getattr(message, 'caption', '') or ''
                message_data['file_path'] = await download_file(message.video)
                logger.info("Channel video message processed")
            elif hasattr(message, 'document') and message.document:
                message_data['message_type'] = 'document'
                message_data['message_content'] = getattr(message, 'caption', '') or ''
                message_data['file_path'] = await download_file(message.document)
                logger.info("Channel document message processed")
            
            logger.info(f"Final channel message data: {message_data}")
            save_message(message_data)
            logger.info(f"Channel message saved to database")
        
        return jsonify({'status': 'success'})

    except Exception as e:
        logger.error(f"Error processing webhook update: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# 添加任务取消方法到TaskManager类
    def cancel_task(self, task_id):
        """取消指定的任务"""
        with self._lock:
            if task_id in self._tasks:
                try:
                    self._tasks[task_id].cancel()
                    logger.info(f"[定时任务] 任务 {task_id} 已取消")
                except Exception as e:
                    logger.error(f"[定时任务] 取消任务 {task_id} 时出错: {str(e)}")
                self._tasks.pop(task_id, None)

    def cleanup(self):
        """清理所有任务"""
        with self._lock:
            for task_id, future in self._tasks.items():
                try:
                    future.cancel()
                    logger.info(f"[定时任务] 任务 {task_id} 已在清理时取消")
                except Exception as e:
                    logger.error(f"[定时任务] 清理任务 {task_id} 时出错: {str(e)}")
            self._tasks.clear()
            logger.info("[定时任务] 所有任务已清理")

# 修改TaskManager的schedule_task方法以支持取消已存在的任务
def schedule_task(self, task_id, func, delay):
    """调度一个延迟执行的任务，如果已存在同ID的任务则先取消"""
    with self._lock:
        # 如果已存在相同ID的任务，先取消它
        if task_id in self._tasks:
            self._tasks[task_id].cancel()
            self._tasks.pop(task_id)
            logger.info(f"[定时任务] 取消已存在的任务 {task_id}")
        
        # 提交新任务
        future = self.executor.submit(self._run_task, task_id, func, delay)
        self._tasks[task_id] = future
        logger.info(f"[定时任务] 已调度任务 {task_id}, 将在 {delay} 秒后执行")
        
def _run_task(self, task_id, func, delay):
    """运行任务的内部方法"""
    try:
        logger.info(f"[定时任务] 开始执行任务 {task_id}, 延迟 {delay} 秒")
        time.sleep(delay)
        
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 创建新的 bot 实例
            request = HTTPXRequest(
                connection_pool_size=1,
                connect_timeout=30.0,
                read_timeout=30.0,
                write_timeout=30.0,
                pool_timeout=3.0
            )
            bot = telegram.Bot(token=TOKEN, request=request)
            
            # 执行异步操作
            coroutine = func(bot)
            result = loop.run_until_complete(coroutine)
            logger.info(f"[定时任务] 任务 {task_id} 执行成功")
            return result
        finally:
            loop.close()
            asyncio.set_event_loop(None)
            
    except asyncio.CancelledError:
        logger.info(f"[定时任务] 任务 {task_id} 被取消")
    except Exception as e:
        logger.error(f"[定时任务] 任务 {task_id} 执行失败: {str(e)}", exc_info=True)
    finally:
        with self._lock:
            self._tasks.pop(task_id, None)
            logger.info(f"[定时任务] 任务 {task_id} 已从队列中移除")
# 新增：验证超时处理函数
async def handle_verification_timeout(bot, chat_id: int, user_id: int):
    """处理验证超时"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 检查用户状态
        c.execute('''
            SELECT status
            FROM pending_members
            WHERE chat_id = ? AND user_id = ?
        ''', (chat_id, user_id))
        
        result = c.fetchone()
        if result and result[0] == 'pending':
            # 更新状态为超时
            c.execute('''
                UPDATE pending_members
                SET status = 'timeout'
                WHERE chat_id = ? AND user_id = ?
            ''', (chat_id, user_id))
            conn.commit()
            
            # 踢出用户
            try:
                await bot.ban_chat_member(
                    chat_id=chat_id,
                    user_id=user_id
                )
                # 立即解封以允许用户再次加入
                await bot.unban_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    only_if_banned=True
                )
                
                # 发送超时通知
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"⏰ 验证超时，用户已被移出群组"
                )
                
            except telegram.error.BadRequest as e:
                logger.error(f"Error kicking user {user_id} from chat {chat_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error handling verification timeout: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()

async def send_auto_delete_message(bot, chat_id, text, parse_mode=None, reply_to_message_id=None, delete_after=15):
    """
    发送一条消息并在指定时间后自动删除
    
    参数:
        bot: 机器人实例
        chat_id: 聊天ID
        text: 消息文本
        parse_mode: 解析模式（可选）
        reply_to_message_id: 回复的消息ID（可选）
        delete_after: 多少秒后删除消息（默认15秒）
    """
    try:
        # 发送消息
        sent_message = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_to_message_id=reply_to_message_id
        )
        
        # 创建一个延时删除任务
        async def delete_message(bot):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=sent_message.message_id)
                logger.info(f"Auto-deleted message {sent_message.message_id} in chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to delete message {sent_message.message_id}: {str(e)}")
        
        task_id = f"delete_msg_{chat_id}_{sent_message.message_id}"
        task_manager.schedule_task(task_id, delete_message, delete_after)
        logger.info(f"Scheduled message {sent_message.message_id} for deletion in {delete_after} seconds")
        
        return sent_message
        
    except Exception as e:
        logger.error(f"Error in send_auto_delete_message: {str(e)}")
        return None
# 修改检查垃圾信息的函数
async def check_spam(message, chat_id):
    """检查消息是否为垃圾信息，支持白名单"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        logger.info(f"[垃圾检测] 开始检查消息: chat_id={chat_id}")
        
        # 首先检查用户是否在白名单中
        user_id = message.from_user.id
        c.execute('''
            SELECT 1 FROM spam_filter_whitelist 
            WHERE chat_id = ? AND user_id = ?
        ''', (chat_id, user_id))
        
        if c.fetchone():
            logger.info(f"[垃圾检测] 用户 {user_id} 在白名单中，跳过检查")
            return False, None
        
        # 获取垃圾信息过滤设置
        c.execute('''
            SELECT enabled, rules
            FROM spam_filter_settings 
            WHERE chat_id = ? AND enabled = 1
        ''', (chat_id,))
        
        row = c.fetchone()
        if not row:
            logger.info(f"[垃圾检测] 未找到启用的过滤规则: chat_id={chat_id}")
            return False, None
        
        enabled, rules = row
        if not enabled:
            logger.info(f"[垃圾检测] 过滤功能未启用: chat_id={chat_id}")
            return False, None
        
        rules = json.loads(rules)
        logger.info(f"[垃圾检测] 加载规则: {rules}")
        
        if not rules:
            logger.info(f"[垃圾检测] 无规则配置: chat_id={chat_id}")
            return False, None
        
        # 检查消息内容
        message_text = message.text or message.caption or ''
        if not message_text:
            logger.info(f"[垃圾检测] 无消息内容")
            return False, None
        
        logger.info(f"[垃圾检测] 检查消息内容: {message_text}")
        
        for rule in rules:
            match_found = False
            action = rule['action']
            
            logger.info(f"[垃圾检测] 检查规则: type={rule['type']}, content={rule['content']}")
            
            if rule['type'] == 'keyword':
                match_found = rule['content'].lower() in message_text.lower()
            elif rule['type'] == 'url':
                if not rule['content'] or rule['content'] == '*':
                    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
                    match_found = bool(re.search(url_pattern, message_text))
                else:
                    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', message_text)
                    match_found = any(rule['content'].lower() in url.lower() for url in urls)
            elif rule['type'] == 'regex':
                try:
                    pattern = re.compile(rule['content'], re.IGNORECASE)
                    match_found = bool(pattern.search(message_text))
                except re.error:
                    logger.error(f"[垃圾检测] 无效的正则表达式: {rule['content']}")
                    continue
            
            if match_found:
                logger.info(f"[垃圾检测] 发现匹配规则: type={rule['type']}, action={action}")
                return True, action
        
        logger.info(f"[垃圾检测] 未发现垃圾信息")
        return False, None
        
    except Exception as e:
        logger.error(f"[垃圾检测] 检查出错: {str(e)}", exc_info=True)
        return False, None
    finally:
        if 'conn' in locals():
            conn.close()

async def handle_verification_success(bot, user_id, group_id, message, welcome_msg, task_id):
    """处理验证成功的情况"""
    try:
        # 解除限制
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )
        await bot.restrict_chat_member(
            chat_id=group_id,
            user_id=user_id,
            permissions=permissions
        )
        logger.info(f"Permissions restored for user {user_id}")
        
        # 发送私聊通过消息（私聊消息不自动删除）
        await bot.send_message(
            chat_id=user_id,
            text="✅ 验证通过！您现在可以在群组内发言了。"
        )
        
        # 在群组发送通过通知（自动删除）
        success_msg = f"✅ 用户 {message.from_user.mention_html()} 已通过验证，欢迎加入！"
        await send_auto_delete_message(
            bot=bot,
            chat_id=group_id,
            text=success_msg,
            parse_mode='HTML'
        )
        
        # 发送欢迎消息（自动删除）
        if welcome_msg:
            await send_auto_delete_message(
                bot=bot,
                chat_id=group_id,
                text=welcome_msg,
                parse_mode='HTML'
            )

        # 尝试取消超时任务
        try:
            task_manager.cancel_task(task_id)
            logger.info(f"Verification completed successfully for user {user_id}")
        except AttributeError:
            logger.warning(f"Could not cancel task {task_id}, but verification was successful")
        except Exception as e:
            logger.error(f"Error canceling task {task_id}: {str(e)}")

    except Exception as e:
        logger.error(f"Error in verification success flow: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=user_id,
            text="❌ 处理验证时出现错误，但您的答案是正确的。请尝试在群组中发言，如果仍有问题请联系管理员。"
        )

# 新增：清理过期验证记录的定时任务
async def clean_expired_verifications():
    """清理过期的验证记录"""
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            # 删除已完成的过期记录
            c.execute('''
                DELETE FROM pending_members
                WHERE status != 'pending'
                AND datetime(verify_deadline) < datetime('now')
            ''')
            
            conn.commit()
            logger.info("Cleaned expired verification records")
            
        except Exception as e:
            logger.error(f"Error cleaning expired verifications: {str(e)}")
        finally:
            if 'conn' in locals():
                conn.close()
            
        # 每小时运行一次
        await asyncio.sleep(3600)

# 获取群组列表
@app.route('/api/groups', methods=['GET'])
@login_required
@async_route
async def get_groups():
    try:
        logger.info("开始获取群组列表")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 从消息记录中获取唯一的群组信息
        c.execute('''
            SELECT DISTINCT chat_id, chat_title 
            FROM messages 
            WHERE chat_type IN ('group', 'supergroup') 
            ORDER BY chat_title
        ''')
        
        groups = [{'id': row[0], 'title': row[1]} for row in c.fetchall()]
        conn.close()
        
        logger.info(f"成功获取群组列表，共 {len(groups)} 个群组")
        for group in groups:
            logger.info(f"群组: {group['title']} (ID: {group['id']})")
        
        return jsonify({
            'status': 'success',
            'groups': groups
        })
    except Exception as e:
        logger.error(f"获取群组列表时发生错误: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# 获取群组成员,由于 Telegram API 的限制，get_chat_members() 可能只能获取最近活跃的成员，而不是所有成员。这是 Telegram 的一个限制，不是代码的问题
@app.route('/api/group_members/<string:chat_id>', methods=['GET'])
@login_required
@async_route
async def get_group_members(chat_id):
    try:
        chat_id_int = int(chat_id)
        logger.info(f"正在获取群组 {chat_id_int} 的成员列表")
        
        async with bot_manager.get_bot() as bot:
            try:
                # 首先检查机器人是否在群组中以及权限
                chat = await bot.get_chat(chat_id_int)
                bot_member = await bot.get_chat_member(chat_id_int, (await bot.get_me()).id)
                logger.info(f"机器人在群组 {chat_id_int} 中的状态: {bot_member.status}")
                
                members = []
                member_count = await bot.get_chat_member_count(chat_id_int)
                logger.info(f"群组 {chat_id_int} 总成员数: {member_count}")
                
                # 获取管理员列表
                admins = await bot.get_chat_administrators(chat_id_int)
                admin_ids = set()
                
                # 将管理员添加到成员列表
                for admin in admins:
                    user = admin.user
                    admin_ids.add(user.id)
                    member_info = {
                        'user_id': user.id,
                        'full_name': user.full_name,
                        'username': user.username,
                        'status': admin.status,
                        'custom_title': getattr(admin, 'custom_title', None),
                        'is_admin': True,
                        'last_active': None
                    }
                    members.append(member_info)
                    logger.info(f"获取到管理员: {user.full_name} ({user.id})")
                
                # 获取最近的消息记录以识别活跃成员
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                
                # 获取最近发送消息的用户ID和最后活跃时间
                c.execute('''
                    SELECT from_user_id, user_name, MAX(timestamp) as last_active
                    FROM messages 
                    WHERE chat_id = ? 
                    AND from_user_id IS NOT NULL 
                    AND from_user_id != 0
                    GROUP BY from_user_id, user_name
                    ORDER BY last_active DESC
                    LIMIT 100
                ''', (chat_id_int,))
                
                active_users = c.fetchall()
                conn.close()
                
                # 获取活跃成员的详细信息
                for user_id, user_name, last_active in active_users:
                    if user_id not in admin_ids:  # 避免重复添加管理员
                        try:
                            member = await bot.get_chat_member(chat_id_int, user_id)
                            if member.status not in ['left', 'kicked']:
                                user = member.user
                                member_info = {
                                    'user_id': user.id,
                                    'full_name': user.full_name or user_name,
                                    'username': user.username,
                                    'status': member.status,
                                    'custom_title': None,
                                    'is_admin': False,
                                    'last_active': last_active
                                }
                                members.append(member_info)
                                logger.info(f"获取到成员: {user.full_name or user_name} ({user.id})")
                        except Exception as e:
                            logger.warning(f"获取成员 {user_id} 信息失败: {str(e)}")
                
                # 按最后活跃时间排序
                members.sort(key=lambda x: (not x['is_admin'], x['last_active'] or ''))
                
                logger.info(f"成功获取群组 {chat_id_int} 的成员列表，共 {len(members)} 名成员（总成员数：{member_count}）")
                return jsonify({
                    'status': 'success',
                    'members': members,
                    'total_members': member_count,
                    'visible_members': len(members),
                    'chat_title': chat.title
                })
                
            except telegram.error.Forbidden as e:
                logger.error(f"没有权限访问群组 {chat_id_int}: {str(e)}")
                return jsonify({
                    'status': 'error',
                    'message': '机器人没有访问该群组的权限'
                }), 403
            except telegram.error.BadRequest as e:
                logger.error(f"无效的群组 ID {chat_id_int}: {str(e)}")
                return jsonify({
                    'status': 'error',
                    'message': '无效的群组ID或群组不存在'
                }), 400
                
    except Exception as e:
        logger.error(f"获取群组 {chat_id} 成员列表时发生错误: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'获取成员列表失败: {str(e)}'
        }), 500
@app.route('/auto_mute/list', methods=['GET'])
@login_required
def list_auto_mute_settings():
    """获取所有自动禁言设置"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute('''
            SELECT 
                chat_id, enabled, start_time, end_time, 
                days_of_week, mute_level, updated_at 
            FROM auto_mute_settings 
            WHERE enabled = 1
            ORDER BY updated_at DESC
        ''')
        rows = c.fetchall()
        
        if rows is None:
            return jsonify({
                'status': 'success',
                'settings': []
            })
        
        settings = []
        for row in rows:
            chat_id, enabled, start_time, end_time, days_of_week, mute_level, updated_at = row
            
            # 转换 updated_at 到北京时间
            if updated_at:
                try:
                    # 先解析UTC时间
                    dt = datetime.strptime(updated_at, '%Y-%m-%d %H:%M:%S')
                    # 添加UTC时区信息
                    dt = dt.replace(tzinfo=pytz.UTC)
                    # 转换到北京时间
                    beijing_dt = dt.astimezone(CHINA_TZ)
                    updated_at = beijing_dt.strftime('%Y-%m-%d %H:%M:%S')
                except Exception as e:
                    logger.error(f"时间转换错误: {str(e)}")
            
            settings.append({
                'chat_id': chat_id,
                'enabled': bool(enabled),
                'start_time': start_time,
                'end_time': end_time,
                'days_of_week': list(map(int, days_of_week.split(','))),
                'mute_level': mute_level,
                'updated_at': updated_at
            })
        
        return jsonify({
            'status': 'success',
            'settings': settings
        })

    except Exception as e:
        logger.error(f"Error fetching auto mute settings: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f"获取设置失败: {str(e)}"
        }), 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/serve_file/<filename>')
@login_required
def serve_file(filename):
    """提供文件下载服务"""
    try:
        file_path = os.path.join(FILES_DIR, filename)
        if os.path.exists(file_path):
            return send_file(file_path)
        else:
            logger.error(f"File not found: {file_path}")
            return "File not found", 404
    except Exception as e:
        logger.error(f"Error serving file {filename}: {str(e)}")
        return "Error serving file", 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        token = request.form.get('token')
        
        if token == ACCESS_TOKEN:
            session['authenticated'] = True
            return redirect(url_for('home'))
        else:
            return jsonify({'error': 'Invalid token'}), 401
            
    return app.send_static_file('login.html')

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
    return render_template('index.html', admin_id=TELEGRAM['ADMIN_ID'])

@app.route('/messages', methods=['GET'])
@login_required
def get_messages():
    try:
        logger.info("Received request for messages")
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        chat_type = request.args.get('chat_type', 'all')
        message_type = request.args.get('message_type', 'all')
        group_id = request.args.get('group_id', 'all')  # 添加群组ID参数
        offset = (page - 1) * per_page
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 构建基础查询
        base_query = """
            SELECT timestamp, chat_id, chat_title, user_name, message_type, 
                   message_content, file_path, COALESCE(from_user_id, '') as from_user_id
            FROM messages
            WHERE 1=1
        """
        count_query = "SELECT COUNT(*) FROM messages WHERE 1=1"
        query_params = []
        
        # 添加过滤条件
        if chat_type != 'all':
            base_query += " AND chat_type = ?"
            count_query += " AND chat_type = ?"
            query_params.append(chat_type)
            
        if message_type != 'all':
            base_query += " AND message_type = ?"
            count_query += " AND message_type = ?"
            query_params.append(message_type)

        if group_id != 'all':
            base_query += " AND chat_id = ?"
            count_query += " AND chat_id = ?"
            query_params.append(group_id)
        
        # 获取总数
        c.execute(count_query, query_params)
        total_count = c.fetchone()[0]
        logger.info(f"Total message count: {total_count}")
        
        # 添加排序和分页
        base_query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        query_params.extend([per_page, offset])
        
        # 执行主查询
        c.execute(base_query, query_params)
        
        messages = []
        for row in c.fetchall():
            message = {
                'timestamp': row[0],
                'chat_id': row[1],
                'chat_title': row[2],
                'user_name': row[3],
                'message_type': row[4],
                'message_content': row[5],
                'file_path': row[6],
                'from_user_id': row[7] if row[7] != '' else None
            }
            messages.append(message)
        
        conn.close()
        
        return jsonify({
            'messages': messages,
            'total': total_count,
            'page': page,
            'per_page': per_page,
            'total_pages': (total_count + per_page - 1) // per_page
        })
    except Exception as e:
        logger.error(f"Error fetching messages: {str(e)}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/send_message', methods=['POST'])
@login_required
@async_route
async def send_message():
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': '无效的请求数据'
            }), 400
            
        chat_id = data.get('chat_id')
        message = data.get('message')
        
        if not chat_id or not message:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数'
            }), 400
        
        try:
            chat_id = int(chat_id)
        except ValueError:
            return jsonify({
                'status': 'error',
                'message': '无效的聊天 ID 格式'
            }), 400

        max_retries = 3
        retry_delays = [0.1, 0.5, 1]
        last_error = None

        for attempt, delay in enumerate(retry_delays):
            try:
                if attempt > 0:
                    await asyncio.sleep(delay)

                async with bot_manager.get_bot() as bot:
                    sent_message = await bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode='HTML',
                        read_timeout=15,
                        write_timeout=15,
                        connect_timeout=15,
                        pool_timeout=5
                    )

                    logger.info(f"Message sent successfully on attempt {attempt + 1}")
                    return jsonify({
                        'status': 'success',
                        'message_id': sent_message.message_id,
                        'attempt': attempt + 1
                    })

            except Forbidden:
                return jsonify({
                    'status': 'error',
                    'message': '机器人没有权限发送消息到该聊天'
                }), 403

            except BadRequest as e:
                return jsonify({
                    'status': 'error',
                    'message': f'无效的请求：{str(e)}'
                }), 400

            except NetworkError as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt == len(retry_delays) - 1:
                    break
                continue

            except Exception as e:
                logger.error(f"Unexpected error in send_message: {str(e)}", exc_info=True)
                last_error = e
                break

        # 如果所有重试都失败
        logger.error(f"All attempts failed: {str(last_error)}")
        return jsonify({
            'status': 'error',
            'message': '发送消息失败，请重试'
        }), 500

    except Exception as e:
        logger.error(f"Error in send_message route: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': '发送失败，请重试'
        }), 500
@app.route('/ban_user', methods=['POST'])
@login_required
@async_route
async def ban_user():
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        user_id = data.get('user_id')
        duration = data.get('duration')  # 可选参数，单位为秒
        
        if not chat_id or not user_id:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数'
            }), 400
            
        try:
            chat_id = int(chat_id)
            user_id = int(user_id)
            if duration:
                duration = int(duration)
        except ValueError:
            return jsonify({
                'status': 'error',
                'message': '无效的ID格式'
            }), 400

        async with bot_manager.get_bot() as bot:
            if duration:
                until_date = datetime.now() + timedelta(seconds=duration)
                await bot.ban_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    until_date=until_date
                )
                message = f'用户已被封禁 {duration} 秒'
            else:
                await bot.ban_chat_member(
                    chat_id=chat_id,
                    user_id=user_id
                )
                message = '用户已被永久封禁'

            return jsonify({
                'status': 'success',
                'message': message
            })

    except Forbidden:
        return jsonify({
            'status': 'error',
            'message': '机器人没有权限执行此操作'
        }), 403
    except BadRequest as e:
        return jsonify({
            'status': 'error',
            'message': f'请求无效：{str(e)}'
        }), 400
    except Exception as e:
        logger.error(f"Error in ban_user: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': '操作失败，请重试'
        }), 500

@app.route('/unban_user', methods=['POST'])
@login_required
@async_route
async def unban_user():
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        user_id = data.get('user_id')
        
        if not chat_id or not user_id:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数'
            }), 400
            
        try:
            chat_id = int(chat_id)
            user_id = int(user_id)
        except ValueError:
            return jsonify({
                'status': 'error',
                'message': '无效的ID格式'
            }), 400

        async with bot_manager.get_bot() as bot:
            await bot.unban_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                only_if_banned=True
            )
            
            return jsonify({
                'status': 'success',
                'message': '用户已解除封禁'
            })

    except Exception as e:
        logger.error(f"Error in unban_user: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': '操作失败，请重试'
        }), 500

# 核心功能实现，不依赖 Flask 上下文
async def _unmute_user_core(bot, chat_id: int, user_id: int):
    """核心解除用户禁言逻辑"""
    try:
        logger.info(f"[解除禁言] 开始解除用户 {user_id} 在群组 {chat_id} 的禁言")
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_change_info=True,
            can_invite_users=True,
            can_pin_messages=True
        )
        
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=permissions
        )
        logger.info(f"[解除禁言] 成功解除用户 {user_id} 的禁言")
        
    except Exception as e:
        logger.error(f"[解除禁言] 解除用户 {user_id} 禁言时出错: {str(e)}", exc_info=True)
        raise

async def _unmute_group_core(bot, chat_id: int):
    """核心解除群组禁言逻辑"""
    try:
        logger.info(f"[解除禁言] 开始解除群组 {chat_id} 的禁言")
        
        request = HTTPXRequest(
            connection_pool_size=1,
            connect_timeout=30.0,
            read_timeout=30.0,
            write_timeout=30.0,
            pool_timeout=3.0
        )
        temp_bot = telegram.Bot(token=bot.token, request=request)
        
        try:
            # 获取当前群组的权限状态
            chat = await temp_bot.get_chat(chat_id)
            current_permissions = chat.permissions
            
            # 定义目标权限状态
            target_permissions = ChatPermissions(
                can_send_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=True,
                can_invite_users=True,
                can_pin_messages=True
            )
            
            # 检查是否需要更改权限
            if (current_permissions.can_send_messages == target_permissions.can_send_messages and
                current_permissions.can_send_polls == target_permissions.can_send_polls and
                current_permissions.can_send_other_messages == target_permissions.can_send_other_messages and
                current_permissions.can_add_web_page_previews == target_permissions.can_add_web_page_previews and
                current_permissions.can_change_info == target_permissions.can_change_info and
                current_permissions.can_invite_users == target_permissions.can_invite_users and
                current_permissions.can_pin_messages == target_permissions.can_pin_messages):
                
                logger.info(f"[解除禁言] 群组 {chat_id} 已经处于解除禁言状态，无需修改")
                return
            
            # 设置新的权限
            await temp_bot.set_chat_permissions(
                chat_id=chat_id,
                permissions=target_permissions
            )

            # 发送解除禁言通知
            notification_text = (
                "🔓 全群禁言已解除\n\n"
                "✅ 现在可以正常发言了\n"
                "📝 如有问题请联系管理员"
            )
            await temp_bot.send_message(
                chat_id=chat_id,
                text=notification_text,
                parse_mode='HTML'
            )
            
            logger.info(f"[解除禁言] 成功解除群组 {chat_id} 的禁言")
            
        except telegram.error.BadRequest as e:
            if 'Chat_not_modified' in str(e):
                logger.info(f"[解除禁言] 群组 {chat_id} 权限未发生变化")
            else:
                raise
            
    except Exception as e:
        logger.error(f"[解除禁言] 解除群组 {chat_id} 禁言时出错: {str(e)}", exc_info=True)
        raise

# Flask 路由处理函数
@app.route('/mute_user', methods=['POST'])
@login_required
@async_route
async def mute_user():
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        user_id = data.get('user_id')
        duration = data.get('duration')  # 单位：秒
        
        if not chat_id or not user_id:
            logger.error("Missing required parameters")
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数'
            }), 400
            
        try:
            chat_id = int(chat_id)
            user_id = int(user_id)
            if duration is not None:
                duration = int(duration)
        except ValueError:
            logger.error("Invalid parameter format")
            return jsonify({
                'status': 'error',
                'message': '无效的参数格式'
            }), 400

        # 设置禁言权限
        permissions = ChatPermissions(
            can_send_messages=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False
        )

        try:
            async with bot_manager.get_bot() as bot:
                # 检查机器人权限
                bot_member = await bot.get_chat_member(chat_id, (await bot.get_me()).id)
                if bot_member.status not in [ChatMemberStatus.ADMINISTRATOR]:
                    logger.error("Bot needs admin rights")
                    return jsonify({
                        'status': 'error',
                        'message': '机器人需要管理员权限'
                    }), 403

                # 执行禁言操作
                await bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=permissions
                )

                # 如果设置了时长，创建定时解除任务
                if duration is not None and duration > 0:
                    logger.info(f"[禁言] 创建用户 {user_id} 的 {duration} 秒自动解除任务")
                    task_id = f"user_mute_{chat_id}_{user_id}"
                    task_manager.schedule_task(
                        task_id,
                        lambda bot: _unmute_user_core(bot, chat_id, user_id),
                        duration
                    )
                    message = f'用户已被禁言 {duration} 秒'
                else:
                    message = '用户已被永久禁言'
                    logger.info(f"[禁言] 用户 {user_id} 被永久禁言")

                return jsonify({
                    'status': 'success',
                    'message': message
                })

        except telegram.error.BadRequest as e:
            error_message = str(e)
            logger.error(f"BadRequest error: {error_message}")
            if "Not enough rights" in error_message:
                return jsonify({
                    'status': 'error',
                    'message': '机器人权限不足'
                }), 403
            return jsonify({
                'status': 'error',
                'message': f'请求无效：{error_message}'
            }), 400

    except Exception as e:
        logger.error(f"Error in mute_user: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': '操作失败，请重试'
        }), 500

@app.route('/mute_all', methods=['POST'])
@login_required
@async_route
async def mute_all():
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        duration = data.get('duration')  # 单位：秒
        mute_level = data.get('mute_level', 'strict')  # 禁言级别参数
        is_auto_mute = data.get('is_auto_mute', False)  # 是否是自动禁言
        
        if not chat_id:
            logger.error("Missing chat_id")
            return jsonify({
                'status': 'error',
                'message': '缺少群组ID'
            }), 400
            
        try:
            chat_id = int(chat_id)
            if duration is not None:
                duration = int(duration)
        except ValueError:
            logger.error("Invalid chat_id format")
            return jsonify({
                'status': 'error',
                'message': '无效的ID格式'
            }), 400

        async with bot_manager.get_bot() as bot:
            # 检查机器人权限
            bot_member = await bot.get_chat_member(chat_id, (await bot.get_me()).id)
            if bot_member.status not in [ChatMemberStatus.ADMINISTRATOR]:
                logger.error("Bot needs admin rights")
                return jsonify({
                    'status': 'error',
                    'message': '机器人需要管理员权限'
                }), 403

            # 使用统一的禁言设置函数
            await _apply_mute_settings(bot, chat_id, mute_level, is_auto_mute, duration)

            # 如果设置了时长，创建定时解除任务
            if duration is not None and duration > 0:
                logger.info(f"[禁言] 创建群组 {chat_id} 的 {duration} 秒自动解除任务")
                task_id = f"group_mute_{chat_id}"
                task_manager.schedule_task(
                    task_id,
                    lambda bot: _unmute_group_core(bot, chat_id),
                    duration
                )
                message = f'已开启{"严格" if mute_level == "strict" else "轻度"}全群禁言 {duration} 秒'
            else:
                message = f'已开启永久{"严格" if mute_level == "strict" else "轻度"}全群禁言'
                logger.info(f"[禁言] 群组 {chat_id} 被永久禁言")

            return jsonify({
                'status': 'success',
                'message': message
            })

    except Exception as e:
        logger.error(f"Error in mute_all: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': '操作失败，请重试'
        }), 500

@app.route('/unmute_user', methods=['POST'])
@login_required
@async_route
async def unmute_user():
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        user_id = data.get('user_id')
        
        if not chat_id or not user_id:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数'
            }), 400
            
        try:
            chat_id = int(chat_id)
            user_id = int(user_id)
        except ValueError:
            return jsonify({
                'status': 'error',
                'message': '无效的ID格式'
            }), 400

        async with bot_manager.get_bot() as bot:
            await _unmute_user_core(bot, chat_id, user_id)
            return jsonify({
                'status': 'success',
                'message': '用户已解除禁言'
            })

    except Exception as e:
        logger.error(f"Error in unmute_user: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': '操作失败，请重试'
        }), 500

@app.route('/unmute_all', methods=['POST'])
@login_required
@async_route
async def unmute_all():
    """解除全群禁言路由处理"""
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        
        if not chat_id:
            return jsonify({
                'status': 'error',
                'message': '缺少群组ID'
            }), 400
            
        try:
            chat_id = int(chat_id)
        except ValueError:
            return jsonify({
                'status': 'error',
                'message': '无效的ID格式'
            }), 400

        # 使用上下文管理器获取bot实例
        async with bot_manager.get_bot() as bot:
            try:
                await _unmute_group_core(bot, chat_id)
                return jsonify({
                    'status': 'success',
                    'message': '已解除全群禁言'
                })
            except telegram.error.BadRequest as e:
                if 'Chat_not_modified' in str(e):
                    return jsonify({
                        'status': 'success',
                        'message': '群组已处于解除禁言状态'
                    })
                raise

    except Exception as e:
        logger.error(f"Error in unmute_all: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': '操作失败，请重试'
        }), 500

@app.route('/spam_filter/settings', methods=['GET', 'POST'])
@login_required
@async_route  # 添加这个装饰器
async def spam_filter_settings():
    """获取或更新垃圾信息过滤设置"""
    try:
        if request.method == 'GET':
            chat_id = request.args.get('chat_id')
            if not chat_id:
                return jsonify({
                    'status': 'error',
                    'message': '缺少群组ID'
                }), 400

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            c.execute('''
                SELECT enabled, rules
                FROM spam_filter_settings 
                WHERE chat_id = ?
            ''', (chat_id,))
            
            row = c.fetchone()
            if row:
                settings = {
                    'enabled': bool(row[0]),
                    'rules': json.loads(row[1] if row[1] else '[]')
                }
            else:
                settings = {
                    'enabled': False,
                    'rules': []
                }
            
            conn.close()
            return jsonify({
                'status': 'success',
                'settings': settings
            })
            
        else:  # POST
            data = request.get_json()
            if not data:
                return jsonify({
                    'status': 'error',
                    'message': '无效的请求数据'
                }), 400

            chat_id = data.get('chat_id')
            enabled = data.get('enabled', False)
            rules = data.get('rules', [])
            
            if not chat_id:
                return jsonify({
                    'status': 'error',
                    'message': '缺少群组ID'
                }), 400

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            now = datetime.now(CHINA_TZ).strftime('%Y-%m-%d %H:%M:%S')
            
            try:
                c.execute('''
                    INSERT INTO spam_filter_settings 
                    (chat_id, enabled, rules, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(chat_id) DO UPDATE SET
                    enabled=excluded.enabled,
                    rules=excluded.rules,
                    updated_at=excluded.updated_at
                ''', (chat_id, enabled, json.dumps(rules), now))
                
                conn.commit()
                
                return jsonify({
                    'status': 'success',
                    'message': '设置已更新'
                })
            finally:
                conn.close()
            
    except Exception as e:
        logger.error(f"Error in spam_filter_settings: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# 新增路由：获取入群设置
@app.route('/join_settings', methods=['GET'])
@login_required
def get_join_settings():
    try:
        chat_id = request.args.get('chat_id')
        if not chat_id:
            return jsonify({
                'status': 'error',
                'message': '缺少群组ID'
            }), 400

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''
            SELECT enabled, verify_type, question, answer, 
                   welcome_message, timeout, updated_at
            FROM join_settings 
            WHERE chat_id = ?
        ''', (chat_id,))
        
        row = c.fetchone()
        if row:
            settings = {
                'enabled': bool(row[0]),
                'verify_type': row[1],
                'question': row[2],
                'answer': row[3],
                'welcome_message': row[4],
                'timeout': row[5],
                'updated_at': row[6]
            }
        else:
            settings = {
                'enabled': False,
                'verify_type': 'question',
                'question': '',
                'answer': '',
                'welcome_message': '',
                'timeout': 300
            }
        
        return jsonify({
            'status': 'success',
            'settings': settings
        })
        
    except Exception as e:
        logger.error(f"Error getting join settings: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    finally:
        if 'conn' in locals():
            conn.close()

# 新增路由：更新入群设置
@app.route('/join_settings', methods=['POST'])
@login_required
@async_route
async def update_join_settings():
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        if not chat_id:
            return jsonify({
                'status': 'error',
                'message': '缺少群组ID'
            }), 400

        enabled = data.get('enabled', False)
        verify_type = data.get('verify_type', 'question')
        question = data.get('question', '')
        answer = data.get('answer', '')
        welcome_message = data.get('welcome_message', '')
        timeout = data.get('timeout', 300)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        now = datetime.now(CHINA_TZ).strftime('%Y-%m-%d %H:%M:%S')
        
        c.execute('''
            INSERT INTO join_settings 
            (chat_id, enabled, verify_type, question, answer, 
             welcome_message, timeout, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
            enabled=excluded.enabled,
            verify_type=excluded.verify_type,
            question=excluded.question,
            answer=excluded.answer,
            welcome_message=excluded.welcome_message,
            timeout=excluded.timeout,
            updated_at=excluded.updated_at
        ''', (chat_id, enabled, verify_type, question, answer, 
              welcome_message, timeout, now))
        
        conn.commit()

        # 如果启用了验证，发送通知到群组
        if enabled:
            async with bot_manager.get_bot() as bot:
                notification = (
                    "📢 入群验证已开启\n\n"
                    f"🔒 验证方式：{'入群问答' if verify_type == 'question' else '管理员审核'}\n"
                    f"⏰ 验证时限：{timeout} 秒\n\n"
                    "ℹ️ 新成员加入时将自动开始验证流程"
                )
                await bot.send_message(
                    chat_id=chat_id,
                    text=notification,
                    parse_mode='HTML'
                )

        return jsonify({
            'status': 'success',
            'message': '设置已更新'
        })
        
    except Exception as e:
        logger.error(f"Error updating join settings: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    finally:
        if 'conn' in locals():
            conn.close()

# 新增路由：获取待验证用户列表
@app.route('/pending_members', methods=['GET'])
@login_required
def get_pending_members():
    try:
        chat_id = request.args.get('chat_id')
        if not chat_id:
            return jsonify({
                'status': 'error',
                'message': '缺少群组ID'
            }), 400

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''
            SELECT user_id, username, full_name, join_time, 
                   verify_deadline, status
            FROM pending_members 
            WHERE chat_id = ? AND status = 'pending'
            ORDER BY join_time DESC
        ''', (chat_id,))
        
        members = []
        for row in c.fetchall():
            members.append({
                'user_id': row[0],
                'username': row[1],
                'full_name': row[2],
                'join_time': row[3],
                'verify_deadline': row[4],
                'status': row[5]
            })
        
        return jsonify({
            'status': 'success',
            'members': members
        })
        
    except Exception as e:
        logger.error(f"Error getting pending members: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    finally:
        if 'conn' in locals():
            conn.close()

# 新增路由：处理验证结果
@app.route('/verify_member', methods=['POST'])
@login_required
@async_route
async def verify_member():
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        user_id = data.get('user_id')
        approved = data.get('approved', False)
        
        if not chat_id or not user_id:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数'
            }), 400

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 更新用户状态
        c.execute('''
            UPDATE pending_members
            SET status = ?
            WHERE chat_id = ? AND user_id = ?
        ''', ('approved' if approved else 'rejected', chat_id, user_id))
        
        conn.commit()

        # 处理验证结果
        async with bot_manager.get_bot() as bot:
            if approved:
                # 解除限制
                permissions = ChatPermissions(
                    can_send_messages=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True
                )
                await bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=permissions
                )
                
                # 发送通过通知
                success_msg = f"✅ 用户已通过管理员验证，欢迎加入！"
                await send_auto_delete_message(
                    bot=bot,
                    chat_id=chat_id,
                    text=success_msg,
                    parse_mode='HTML'
                )
                
                # 查询欢迎消息
                c.execute('''
                    SELECT welcome_message
                    FROM join_settings 
                    WHERE chat_id = ?
                ''', (chat_id,))
                result = c.fetchone()
                if result and result[0]:
                    welcome_msg = result[0]
                    await send_auto_delete_message(
                        bot=bot,
                        chat_id=chat_id,
                        text=welcome_msg,
                        parse_mode='HTML'
                    )
            else:
                # 移出用户
                await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
                
                # 发送拒绝通知
                reject_msg = "❌ 管理员已拒绝验证请求"
                await send_auto_delete_message(
                    bot=bot,
                    chat_id=chat_id,
                    text=reject_msg
                )

        return jsonify({
            'status': 'success',
            'message': '验证处理完成'
        })
        
    except Exception as e:
        logger.error(f"Error verifying member: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    finally:
        if 'conn' in locals():
            conn.close()

# 新增白名单相关路由
@app.route('/spam_filter/whitelist', methods=['GET'])
@login_required
def get_whitelist():
    """获取垃圾信息过滤白名单"""
    try:
        chat_id = request.args.get('chat_id')
        if not chat_id:
            return jsonify({
                'status': 'error',
                'message': '缺少群组ID'
            }), 400

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''
            SELECT user_id, username, full_name, added_by, added_at, note
            FROM spam_filter_whitelist 
            WHERE chat_id = ?
            ORDER BY added_at DESC
        ''', (chat_id,))
        
        whitelist = [{
            'user_id': row[0],
            'username': row[1],
            'full_name': row[2],
            'added_by': row[3],
            'added_at': row[4],
            'note': row[5]
        } for row in c.fetchall()]
        
        return jsonify({
            'status': 'success',
            'whitelist': whitelist
        })
        
    except Exception as e:
        logger.error(f"Error getting whitelist: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    finally:
        if 'conn' in locals():
            conn.close()

# 修改添加到白名单的路由
@app.route('/spam_filter/whitelist', methods=['POST'])
@login_required
@async_route  # 添加这个装饰器
async def add_to_whitelist():
    """添加用户到白名单"""
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        user_id = data.get('user_id')
        added_by = data.get('added_by')  # 管理员ID
        note = data.get('note', '')
        
        if not all([chat_id, user_id, added_by]):
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数'
            }), 400

        # 获取用户信息
        async with bot_manager.get_bot() as bot:
            try:
                chat_member = await bot.get_chat_member(chat_id, user_id)
                user = chat_member.user
                username = user.username
                full_name = user.full_name
            except Exception as e:
                logger.error(f"Error getting user info: {str(e)}")
                username = None
                full_name = None

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        try:
            c.execute('''
                INSERT INTO spam_filter_whitelist 
                (chat_id, user_id, username, full_name, added_by, note)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (chat_id, user_id, username, full_name, added_by, note))
            
            conn.commit()
            
            return jsonify({
                'status': 'success',
                'message': '用户已添加到白名单'
            })
            
        except sqlite3.IntegrityError:
            return jsonify({
                'status': 'error',
                'message': '该用户已在白名单中'
            }), 400
            
    except Exception as e:
        logger.error(f"Error adding to whitelist: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/spam_filter/whitelist', methods=['DELETE'])
@login_required
def remove_from_whitelist():
    """从白名单中移除用户"""
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        user_id = data.get('user_id')
        
        if not all([chat_id, user_id]):
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数'
            }), 400

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''
            DELETE FROM spam_filter_whitelist 
            WHERE chat_id = ? AND user_id = ?
        ''', (chat_id, user_id))
        
        conn.commit()
        
        if c.rowcount == 0:
            return jsonify({
                'status': 'error',
                'message': '用户不在白名单中'
            }), 404
        
        return jsonify({
            'status': 'success',
            'message': '用户已从白名单中移除'
        })
        
    except Exception as e:
        logger.error(f"Error removing from whitelist: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    finally:
        if 'conn' in locals():
            conn.close()

async def init_app():
    """初始化应用"""
    try:
        # 初始化 bot
        await bot_manager.initialize()
        # 设置 webhook
        async with bot_manager.get_bot() as bot:
            # 先获取当前的 webhook 信息
            webhook_info = await bot.get_webhook_info()
            logger.info(f"Current webhook info: {webhook_info.to_dict()}")
            
            # 删除现有的 webhook
            await bot.delete_webhook()
            logger.info("Deleted existing webhook")
            
            # 使用配置文件中的 WEBHOOK_URL
            success = await bot.set_webhook(
                url=TELEGRAM['WEBHOOK_URL'],  # 修改这里
                allowed_updates=['message', 'edited_message', 'channel_post', 'edited_channel_post']
            )
            
            if success:
                logger.info(f"Successfully set webhook to: {TELEGRAM['WEBHOOK_URL']}")  # 这里也要修改
                # 验证设置
                new_webhook_info = await bot.get_webhook_info()
                logger.info(f"New webhook info: {new_webhook_info.to_dict()}")
            else:
                logger.error("Failed to set webhook")
                
    except Exception as e:
        logger.error(f"Failed to initialize app: {str(e)}", exc_info=True)
        raise
async def _apply_mute_settings(bot, chat_id: int, mute_level: str, is_auto_mute: bool = False, duration: int = None):
    """应用禁言设置的核心函数"""
    permissions = ChatPermissions(
        can_send_messages=mute_level != 'strict',
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
        can_change_info=False,
        can_invite_users=False,
        can_pin_messages=False
    )
    
    # 设置权限
    await bot.set_chat_permissions(
        chat_id=chat_id,
        permissions=permissions
    )
    
    # 只有在不是自动禁言的情况下才发送常规禁言通知
    if not is_auto_mute:
        notification_text = (
            f"🔒 全群{mute_level == 'strict' and '严格' or '轻度'}禁言已开启\n\n"
            f"⏰ 禁言时长：{duration and f'{duration} 秒' or '永久'}\n"
            f"📝 禁言级别：{mute_level == 'strict' and '严格（禁止所有消息）' or '轻度（仅允许文字消息）'}\n\n"
            "⚠️ 请各位成员注意"
        )
        await bot.send_message(
            chat_id=chat_id,
            text=notification_text,
            parse_mode='HTML'
        )

async def check_auto_mute():
    """检查并执行自动禁言"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 获取所有启用了自动禁言的设置
        c.execute('SELECT * FROM auto_mute_settings WHERE enabled = 1')
        settings = c.fetchall()
        
        # 使用北京时间
        now = datetime.now(CHINA_TZ)
        
        for row in settings:
            chat_id = row[1]
            start_time = datetime.strptime(row[3], '%H:%M').time()
            end_time = datetime.strptime(row[4], '%H:%M').time()
            days_of_week = [int(d) for d in row[5].split(',')]
            mute_level = row[6]
            
            current_time = now.time()
            current_day = now.weekday()
            
            # 检查是否在设定的日期内
            if current_day not in days_of_week:
                continue
            
            def is_exact_time(current, target):
                """检查是否恰好是目标时间（精确到分钟）"""
                return (current.hour == target.hour and 
                       current.minute == target.minute and
                       current.second < 30)
            
            try:
                async with bot_manager.get_bot() as bot:
                    start_match = is_exact_time(current_time, start_time)
                    end_match = is_exact_time(current_time, end_time)
                    
                    if start_match:
                        logger.info(f"[自动禁言] 群组 {chat_id} 开始禁言 - 禁言时间：{row[3]} - {row[4]}")
                        
                        # 设置禁言
                        permissions = ChatPermissions(
                            can_send_messages=mute_level != 'strict',
                            can_send_polls=False,
                            can_send_other_messages=False,
                            can_add_web_page_previews=False,
                            can_change_info=False,
                            can_invite_users=False,
                            can_pin_messages=False
                        )
                        
                        await bot.set_chat_permissions(
                            chat_id=chat_id,
                            permissions=permissions
                        )
                        
                        # 发送开启通知
                        notification_text = (
                            "🌙 自动禁言模式已开始\n\n"
                            f"⏰ 禁言时段：{row[3]} - {row[4]}\n"
                            f"📅 生效日期：{formatDays(days_of_week)}\n"
                            f"🔒 禁言级别：{mute_level == 'strict' and '严格（禁止所有消息）' or '轻度（仅允许文字消息）'}\n\n"
                            "⚠️ 请各位成员注意休息"
                        )
                        await bot.send_message(
                            chat_id=chat_id,
                            text=notification_text,
                            parse_mode='HTML'
                        )
                            
                    elif end_match:
                        logger.info(f"[自动禁言] 群组 {chat_id} 解除禁言")
                        
                        # 解除禁言
                        permissions = ChatPermissions(
                            can_send_messages=True,
                            can_send_polls=True,
                            can_send_other_messages=True,
                            can_add_web_page_previews=True,
                            can_change_info=True,
                            can_invite_users=True,
                            can_pin_messages=True
                        )
                        
                        await bot.set_chat_permissions(
                            chat_id=chat_id,
                            permissions=permissions
                        )
                        
                        # 发送解除通知
                        notification_text = (
                            "🌅 自动禁言模式已结束\n\n"
                            "✅ 现在可以正常发言了\n"
                            "📝 如有问题请联系管理员"
                        )
                        await bot.send_message(
                            chat_id=chat_id,
                            text=notification_text,
                            parse_mode='HTML'
                        )
                    
            except Exception as e:
                logger.error(f"[自动禁言] 群组 {chat_id} 操作失败: {str(e)}")
                
    except Exception as e:
        logger.error(f"[自动禁言] 检查过程出错: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()

def formatDays(days):
    """格式化星期显示"""
    day_names = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
    return '、'.join(day_names[day] for day in days)

async def auto_mute_scheduler():
    """自动禁言调度器"""
    logger.info("[自动禁言] 调度器已启动")
    while True:
        try:
            await check_auto_mute()
        except Exception as e:
            logger.error(f"[自动禁言] 调度器错误: {str(e)}")
        finally:
            # 等待到下一分钟的整点
            now = datetime.now(CHINA_TZ)
            next_minute = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
            sleep_seconds = (next_minute - now).total_seconds()
            await asyncio.sleep(sleep_seconds)

if __name__ == '__main__':
    # 初始化目录
    init_directories()
    
    # 初始化数据库
    init_db()
    
    # 创建新的事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def main():
        try:
            logger.info("=== 服务器启动 ===")
            
            # 创建任务列表
            tasks = []
            
            # 初始化应用
            app_task = asyncio.create_task(init_app())
            tasks.append(app_task)
            
            # 启动自动禁言调度器
            scheduler_task = asyncio.create_task(auto_mute_scheduler())
            tasks.append(scheduler_task)
            
            # 启动过期验证清理任务
            cleaner_task = asyncio.create_task(clean_expired_verifications())
            tasks.append(cleaner_task)
            
            # 启动 Flask 应用
            from threading import Thread
            def run_flask():
                app.run(
                    host=SERVER['HOST'], 
                    port=SERVER['PORT'], 
                    use_reloader=False
                )
            
            flask_thread = Thread(target=run_flask)
            flask_thread.daemon = True
            flask_thread.start()
            
            logger.info("Flask 应用已启动")
            logger.info("自动禁言调度器已启动")
            logger.info("验证记录清理任务已启动")
            
            # 等待所有任务完成
            await asyncio.gather(*tasks)
            
        except Exception as e:
            logger.error(f"启动错误: {str(e)}", exc_info=True)
            raise
    
    # 优雅关闭处理
    def signal_handler(sig, frame):
        logger.info("接收到关闭信号，正在关闭服务器...")
        for task in asyncio.all_tasks(loop):
            task.cancel()
        loop.stop()
        loop.close()
        logger.info("服务器已关闭")
        sys.exit(0)
    
    import signal
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 运行程序
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("正在关闭服务器...")
    except Exception as e:
        logger.error(f"致命错误: {str(e)}", exc_info=True)
        raise
    finally:
        logger.info("正在清理资源...")
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        
        try:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
        except Exception as e:
            logger.error(f"清理过程中出错: {str(e)}", exc_info=True)
        
        logger.info("服务器已完全关闭")