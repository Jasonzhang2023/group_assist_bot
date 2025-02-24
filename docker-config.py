import os

# 基础目录配置
BASE_DIR = '/app'  # Docker 环境中的应用根目录

# 确保所需目录存在
LOG_DIR = os.path.join(BASE_DIR, 'logs')
DB_DIR = os.path.join(BASE_DIR, 'data')
FILES_DIR = os.path.join(DB_DIR, 'files')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

# Telegram 机器人配置
TELEGRAM = {
    'BOT_TOKEN': 'YOUR_BOT_TOKEN',  # 替换为你的bot token
    'ADMIN_ID': 123456789,          # 替换为你的管理员ID（整数）
    'WEBHOOK_URL': 'https://your-domain.com/webhook'  # 替换为你的webhook URL
}

# Web服务器配置
SERVER = {
    'HOST': '0.0.0.0',  # 使用0.0.0.0以允许外部访问
    'PORT': 15001,
    'SECRET_KEY': 'your-super-secret-key-here',  # 替换为你的密钥
    'ACCESS_TOKEN': 'your-access-token'          # 替换为你的访问令牌
}

# 数据库配置
DATABASE = {
    'PATH': os.path.join(DB_DIR, 'messages.db')
}

# HTTP 客户端配置
HTTP = {
    'CONNECT_TIMEOUT': 30.0,
    'READ_TIMEOUT': 30.0,
    'WRITE_TIMEOUT': 30.0,
    'POOL_TIMEOUT': 3.0,
    'CONNECTION_POOL_SIZE': 100
}

# 日志配置
LOGGING = {
    'FILE_PATH': os.path.join(LOG_DIR, 'telegram_bot.log'),
    'MAX_BYTES': 250*1024*1024,
    'BACKUP_COUNT': 10,
    'LEVEL': 'INFO'
}

# 时区配置
TIMEZONE = 'Asia/Shanghai'

# 系统默认值配置
DEFAULTS = {
    'VERIFICATION_TIMEOUT': 300,  # 入群验证超时时间（秒）
    'AUTO_DELETE_MESSAGE': 15,    # 自动删除消息时间（秒）
    'THREAD_POOL_SIZE': 10        # 线程池大小
}

# 静态文件配置
STATIC = {
    'FOLDER': STATIC_DIR,
    'URL_PATH': '/static'
}

# 模板目录配置
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')

# 目录列表
directories = [
    BASE_DIR,
    LOG_DIR,
    DB_DIR,
    FILES_DIR,
    TEMPLATE_DIR
]