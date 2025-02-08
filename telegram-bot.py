from flask import Flask, request, jsonify, session, redirect, url_for, send_file
from datetime import timedelta  # 如果还没有这个导入的话
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
from datetime import datetime
from contextlib import asynccontextmanager
from telegram.error import NetworkError, Forbidden, BadRequest

# 初始化 Flask 应用
app = Flask(__name__, 
    static_folder='/home/tel_group_ass/static',
    static_url_path='/static')

# 基础目录配置
BASE_DIR = '/home/tel_group_ass'
LOG_DIR = os.path.join(BASE_DIR, 'logs')
DB_DIR = os.path.join(BASE_DIR, 'data')

# 创建必要的目录
Path(BASE_DIR).mkdir(exist_ok=True)
Path(LOG_DIR).mkdir(exist_ok=True)
Path(DB_DIR).mkdir(exist_ok=True)

# 配置日志系统
log_file = os.path.join(LOG_DIR, 'telegram_bot.log')
handler = RotatingFileHandler(log_file, maxBytes=250*1024*1024, backupCount=10)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# 机器人配置
TOKEN = "8020583467:AAESJ34mM9sO76oSAGCjUggtfxh8ckUccdQ"
ADMIN_ID = 558497162
WEBHOOK_URL = "https://groupass.cfacca.com/webhook"

# Bot 管理器类
class TelegramBotManager:
    def __init__(self, token):
        self.token = token
        self._request = HTTPXRequest(
            connection_pool_size=100,
            connect_timeout=30.0,
            read_timeout=30.0,
            write_timeout=30.0,
            pool_timeout=3.0
        )
        self.bot = telegram.Bot(token=token, request=self._request)
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self):
        async with self._lock:
            if not self._initialized:
                try:
                    await self.bot.get_me()
                    self._initialized = True
                    logger.info("Bot connection pool warmed up successfully")
                except Exception as e:
                    logger.error(f"Failed to warm up bot connection pool: {e}")

    @asynccontextmanager
    async def get_bot(self):
        if not self._initialized:
            await self.initialize()
        try:
            yield self.bot
        except Exception as e:
            logger.error(f"Error in bot operation: {e}")
            raise

# 创建全局 bot 管理器
bot_manager = TelegramBotManager(TOKEN)

# 初始化 Flask 应用
app = Flask(__name__)
app.secret_key = 'your-super-secret-key-here'

# 设置访问令牌
ACCESS_TOKEN = "dongjie19861224"

# 数据库配置
DB_PATH = os.path.join(DB_DIR, 'messages.db')

def async_route(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(f(*args, **kwargs))
    return wrapped

def init_db():
    """初始化数据库"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 首先检查表是否存在
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
        table_exists = c.fetchone() is not None
        
        if not table_exists:
            # 如果表不存在，创建新表
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
        else:
            # 如果表存在，检查并添加缺失的列
            c.execute("PRAGMA table_info(messages)")
            existing_columns = {column[1] for column in c.fetchall()}
            
            # 检查并添加 from_user_id 列
            if 'from_user_id' not in existing_columns:
                c.execute('ALTER TABLE messages ADD COLUMN from_user_id INTEGER')
                logger.info("Added from_user_id column to existing table")
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        # 添加更详细的错误日志
        logger.error(f"Error details:", exc_info=True)
        try:
            conn.rollback()
        except:
            pass
        finally:
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
            message_data.get('from_user_id'),  # 添加用户ID
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
        # 生成文件名，包含文件扩展名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_ext = '.jpg'  # 默认扩展名
        file_path_on_tg = None

        # 获取文件信息
        try:
            async with bot_manager.get_bot() as bot:
                file_info = await bot.get_file(file.file_id)
                file_path_on_tg = file_info.file_path
                if file_path_on_tg:
                    file_ext = os.path.splitext(file_path_on_tg)[1] or '.jpg'
        except Exception as e:
            logger.warning(f"Could not get file info through bot API: {e}, using direct download")
            
        # 构建本地文件路径
        filename = f'{timestamp}_{file.file_unique_id}{file_ext}'
        file_path = os.path.join(DB_DIR, 'files', filename)
        web_path = f'/serve_file/{filename}'
        
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # 设置较大的超时时间
        timeout = httpx.Timeout(30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            # 如果有文件路径，使用正常下载，否则尝试直接下载
            if file_path_on_tg:
                download_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path_on_tg}"
            else:
                download_url = f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={file.file_id}"
            
            logger.info(f"Attempting to download file from: {download_url}")
            response = await client.get(download_url)
            
            if response.status_code == 200:
                # 写入文件
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                
                # 设置文件权限
                os.chmod(file_path, 0o644)
                logger.info(f"File downloaded successfully - Path: {file_path}, Web path: {web_path}")
                return web_path
            else:
                logger.error(f"Failed to download file. Status code: {response.status_code}")
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
            user_id = None  # 初始化用户ID
            
            if user:
                user_full_name = user.full_name or f"{user.first_name or ''} {user.last_name or ''}".strip() or "未知用户"
                user_name = user.username or user_full_name
                user_id = user.id  # 获取用户ID
            
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
                    hasattr(message.reply_to_message, 'forum_topic_created') and 
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
                'from_user_id': user_id,  # 保存用户ID
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
        offset = (page - 1) * per_page
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 首先检查数据表结构
        c.execute("PRAGMA table_info(messages)")
        columns = [column[1] for column in c.fetchall()]
        
        # 获取总数
        c.execute("SELECT COUNT(*) FROM messages")
        total_count = c.fetchone()[0]
        logger.info(f"Total message count: {total_count}")
        
        # 构建查询语句，确保包含 from_user_id
        query = """
            SELECT timestamp, chat_id, chat_title, user_name, message_type, 
                   message_content, file_path, COALESCE(from_user_id, '') as from_user_id
            FROM messages 
            ORDER BY timestamp DESC 
            LIMIT ? OFFSET ?
        """
        
        c.execute(query, (per_page, offset))
        
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
@async_route  # 保留这个装饰器！
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

@app.route('/mute_user', methods=['POST'])
@login_required
@async_route
async def mute_user():
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

        # 修改权限设置
        permissions = telegram.ChatPermissions(
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
                if duration:
                    until_date = datetime.now() + timedelta(seconds=duration)
                    await bot.restrict_chat_member(
                        chat_id=chat_id,
                        user_id=user_id,
                        permissions=permissions,
                        until_date=until_date
                    )
                    message = f'用户已被禁言 {duration} 秒'
                else:
                    await bot.restrict_chat_member(
                        chat_id=chat_id,
                        user_id=user_id,
                        permissions=permissions
                    )
                    message = '用户已被永久禁言'

                return jsonify({
                    'status': 'success',
                    'message': message
                })
        except telegram.error.Forbidden:
            return jsonify({
                'status': 'error',
                'message': '机器人没有权限执行此操作'
            }), 403
        except telegram.error.BadRequest as e:
            return jsonify({
                'status': 'error',
                'message': f'请求无效：{str(e)}'
            }), 400
        except telegram.error.NetworkError as e:
            logger.error(f"Network error in mute_user: {str(e)}", exc_info=True)
            return jsonify({
                'status': 'error',
                'message': '网络错误，请重试'
            }), 500

    except Exception as e:
        logger.error(f"Error in mute_user: {str(e)}", exc_info=True)
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

        # 修改权限设置
        permissions = telegram.ChatPermissions(
            can_send_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_change_info=True,
            can_invite_users=True,
            can_pin_messages=True
        )

        async with bot_manager.get_bot() as bot:
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=permissions
            )
            
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


@app.route('/mute_all', methods=['POST'])
@login_required
@async_route
async def mute_all():
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        duration = data.get('duration')  # 获取duration参数
        
        if not chat_id:
            return jsonify({
                'status': 'error',
                'message': '缺少群组ID'
            }), 400
            
        try:
            chat_id = int(chat_id)
            if duration:
                duration = int(duration)  # 确保duration是整数
        except ValueError:
            return jsonify({
                'status': 'error',
                'message': '无效的ID格式'
            }), 400

        permissions = telegram.ChatPermissions(
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
                if duration:
                    until_date = datetime.now() + timedelta(seconds=duration)
                    await bot.set_chat_permissions(
                        chat_id=chat_id,
                        permissions=permissions,
                        until_date=until_date  # 添加until_date参数
                    )
                    message = f'已开启全群禁言 {duration} 秒'
                else:
                    await bot.set_chat_permissions(
                        chat_id=chat_id,
                        permissions=permissions
                    )
                    message = '已开启永久全群禁言'

                return jsonify({
                    'status': 'success',
                    'message': message
                })
                
        except telegram.error.Forbidden:
            return jsonify({
                'status': 'error',
                'message': '机器人没有权限执行此操作'
            }), 403
        except telegram.error.BadRequest as e:
            return jsonify({
                'status': 'error',
                'message': f'请求无效：{str(e)}'
            }), 400

    except Exception as e:
        logger.error(f"Error in mute_all: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': '操作失败，请重试'
        }), 500

@app.route('/unmute_all', methods=['POST'])
@login_required
@async_route
async def unmute_all():
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

        # 恢复所有权限
        permissions = telegram.ChatPermissions(
            can_send_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_change_info=True,
            can_invite_users=True,
            can_pin_messages=True
        )

        async with bot_manager.get_bot() as bot:
            await bot.set_chat_permissions(
                chat_id=chat_id,
                permissions=permissions
            )
            
            return jsonify({
                'status': 'success',
                'message': '已解除全群禁言'
            })

    except Exception as e:
        logger.error(f"Error in unmute_all: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': '操作失败，请重试'
        }), 500


@app.route('/serve_file/<path:filename>')
@login_required
def serve_file(filename):
    """提供文件访问服务"""
    try:
        file_path = os.path.join(DB_DIR, 'files', filename)
        logger.info(f"Serving file: {file_path}")
        
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return "File not found", 404
        
        # 根据文件扩展名设置正确的 MIME 类型
        mime_type = 'application/octet-stream'
        if filename.lower().endswith(('.jpg', '.jpeg')):
            mime_type = 'image/jpeg'
        elif filename.lower().endswith('.png'):
            mime_type = 'image/png'
        elif filename.lower().endswith('.webp'):
            mime_type = 'image/webp'
        elif filename.lower().endswith('.mp4'):
            mime_type = 'video/mp4'
        
        logger.info(f"Serving file with MIME type: {mime_type}")
        
        response = send_file(
            file_path,
            mimetype=mime_type,
            as_attachment=False,
            download_name=filename
        )
        
        # 添加必要的响应头
        response.headers['Content-Type'] = mime_type
        response.headers['Cache-Control'] = 'public, max-age=31536000'
        response.headers['Access-Control-Allow-Origin'] = '*'
        
        return response
    except Exception as e:
        logger.error(f"Error serving file: {str(e)}", exc_info=True)
        return str(e), 500


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

if __name__ == '__main__':
    # 初始化数据库
    init_db()
    
    # 使用单个事件循环来处理所有初始化
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    async def main():
        with app.app_context():
            await init_app()
    
    # 运行初始化
    loop.run_until_complete(main())
    
    # 启动 Flask 应用
    app.run(host='127.0.0.1', port=15001)