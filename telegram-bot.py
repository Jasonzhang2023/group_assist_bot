from flask import Flask, request, jsonify, session, redirect, url_for, send_file
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


# 基础目录配置
BASE_DIR = '/home/tel_group_ass'
LOG_DIR = os.path.join(BASE_DIR, 'logs')
DB_DIR = os.path.join(BASE_DIR, 'data')
FILES_DIR = os.path.join(DB_DIR, 'files')

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
CHINA_TZ = pytz.timezone('Asia/Shanghai')
# 先创建目录
init_directories()

# 然后配置日志系统
log_file = os.path.join(LOG_DIR, 'telegram_bot.log')
handler = RotatingFileHandler(log_file, maxBytes=250*1024*1024, backupCount=10)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(handler)


# 机器人配置
TOKEN = "your-token"
ADMIN_ID = 66666666
WEBHOOK_URL = "https://your.website.com/webhook"

# Bot 管理器类
class TelegramBotManager:
    def __init__(self, token):
        self.token = token
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
                        connection_pool_size=100,
                        connect_timeout=30.0,
                        read_timeout=30.0,
                        write_timeout=30.0,
                        pool_timeout=3.0
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
bot_manager = TelegramBotManager(TOKEN)

# 初始化 Flask 应用
app = Flask(__name__,
    static_folder='/home/tel_group_ass/static',
    static_url_path='/static')
app.secret_key = 'your-super-secret-key-here'

# 设置访问令牌
ACCESS_TOKEN = "passwall"

# 数据库配置
DB_PATH = os.path.join(DB_DIR, 'messages.db')

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
                    
            except Exception as e:
                logger.error(f"[定时任务] 任务 {task_id} 执行失败: {str(e)}", exc_info=True)
            finally:
                with self._lock:
                    self._tasks.pop(task_id, None)
                    logger.info(f"[定时任务] 任务 {task_id} 已从队列中移除")

        with self._lock:
            # 如果已存在相同ID的任务，先取消它
            if task_id in self._tasks:
                self._tasks[task_id].cancel()
                logger.info(f"[定时任务] 取消已存在的任务 {task_id}")
            
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
                    actual_path = actual_path.split("/file/bot" + TOKEN + "/")[-1]
                
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
        download_url = f"https://api.telegram.org/file/bot{TOKEN}/{actual_path}"
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
        
        if update.message or update.channel_post:
            message = update.channel_post if update.channel_post else update.message
            chat_id = message.chat.id
            chat_type = message.chat.type
            
            logger.info(f"Processing message from chat {chat_id} of type {chat_type}")
            
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
            
            return jsonify({'status': 'success'})
        else:
            logger.info("Update contains no message or channel post")
            return jsonify({'status': 'success', 'message': 'No message or channel post in update'})
            
    except Exception as e:
        logger.error(f"Error processing update: {str(e)}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)})

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
    return app.send_static_file('index.html')

@app.route('/messages', methods=['GET'])
@login_required
def get_messages():
    try:
        logger.info("Received request for messages")
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        chat_type = request.args.get('chat_type', 'all')
        message_type = request.args.get('message_type', 'all')
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
            
            # 设置新的 webhook
            success = await bot.set_webhook(
                url=WEBHOOK_URL,
                allowed_updates=['message', 'edited_message', 'channel_post', 'edited_channel_post']
            )
            
            if success:
                logger.info(f"Successfully set webhook to: {WEBHOOK_URL}")
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
            
            # 创建一个任务列表
            tasks = []
            
            # 初始化应用
            app_task = asyncio.create_task(init_app())
            tasks.append(app_task)
            
            # 启动自动禁言调度器
            scheduler_task = asyncio.create_task(auto_mute_scheduler())
            tasks.append(scheduler_task)
            
            # 启动 Flask 应用（在单独的线程中运行）
            from threading import Thread
            def run_flask():
                app.run(host='127.0.0.1', port=15001, use_reloader=False)
            
            flask_thread = Thread(target=run_flask)
            flask_thread.daemon = True
            flask_thread.start()
            
            logger.info("Flask 应用已启动")
            logger.info("自动禁言调度器已启动")
            
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