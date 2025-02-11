// messages.js
let currentPage = 1;
let totalPages = 1;
let autoRefreshInterval;
let currentFilters = {
    chatType: 'all',
    messageType: 'all'
};

// 格式化时间戳
function formatTimestamp(timestamp) {
    try {
        const date = new Date(timestamp);
        return date.toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    } catch (e) {
        console.error('Error formatting timestamp:', e);
        return timestamp;
    }
}

// 创建媒体内容
function createMediaContent(msg) {
    if (!msg.file_path) {
        return '';
    }

    const fullPath = msg.file_path.startsWith('/') ? msg.file_path : '/' + msg.file_path;
    
    switch(msg.message_type) {
        case 'photo':
            return `<div class="media-content">
                <img src="${fullPath}" alt="Photo" loading="lazy" onerror="handleImageError(this)">
            </div>`;
        case 'video':
            return `<div class="media-content">
                <video controls onerror="handleVideoError(this)">
                    <source src="${fullPath}" type="video/mp4">
                    您的浏览器不支持视频标签。
                </video>
            </div>`;
        case 'document':
            return `<div class="media-content">
                <a href="${fullPath}" target="_blank" class="file-link">
                    📎 查看文件
                </a>
            </div>`;
        case 'sticker':
            return `<div class="media-content">
                <img src="${fullPath}" alt="Sticker" loading="lazy" onerror="handleImageError(this)">
            </div>`;
        default:
            return '';
    }
}

// 创建消息元素
function createMessageElement(msg) {
    const messageElement = document.createElement('div');
    messageElement.className = 'message';
    
    // 确保 from_user_id 存在且不为空
    const hasUserId = msg.from_user_id && msg.from_user_id !== 'null' && msg.from_user_id !== 'undefined';
    
    let badgesHtml = `
        <span class="badge type-badge">${msg.message_type}</span>
        <span class="badge chat-badge">Chat ID: ${msg.chat_id}</span>
        ${hasUserId ? `<span class="badge user-badge">User ID: ${msg.from_user_id}</span>` : ''}
    `;
    
    messageElement.innerHTML = `
        <div class="message-header">
            <div class="message-meta">
                ${badgesHtml}
                <span class="chat-title">${msg.chat_title}</span>
                <span class="user-name">@${msg.user_name}</span>
            </div>
            <span class="timestamp">${formatTimestamp(msg.timestamp)}</span>
        </div>
        <div class="message-content">
            ${msg.message_content}
            ${createMediaContent(msg)}
        </div>
        <div class="message-actions">
            <button class="reply-button" onclick="handleReply('${msg.chat_id}')">回复此聊天</button>
            ${hasUserId ? `
                <button class="mute-button" onclick="fillMuteForm('${msg.chat_id}', '${msg.from_user_id}')">
                    禁言此用户
                </button>
            ` : ''}
        </div>
    `;
    
    return messageElement;
}

// 填充禁言表单
function fillMuteForm(chatId, userId) {
    const event = new CustomEvent('fillMuteForm', {
        detail: {
            chatId: chatId,
            userId: userId
        }
    });
    window.dispatchEvent(event);
    
    setTimeout(() => {
        const adminPanel = document.getElementById('groupAdminRoot');
        if (adminPanel) {
            adminPanel.scrollIntoView({ behavior: 'smooth' });
        }
    }, 100);
}

// 处理回复操作
function handleReply(chatId) {
    // 填充聊天ID
    const chatIdInput = document.getElementById('chatId');
    if (chatIdInput) {
        chatIdInput.value = chatId;
    }

    // 聚焦到消息内容输入框
    const messageInput = document.getElementById('messageContent');
    if (messageInput) {
        messageInput.focus();
    }

    // 滚动到发送消息表单
    const messageForm = document.querySelector('.message-form');
    if (messageForm) {
        messageForm.scrollIntoView({ behavior: 'smooth' });
    }
}

// 处理媒体错误
function handleImageError(img) {
    console.error('Image failed to load:', img.src);
    img.style.display = 'none';
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message';
    errorDiv.textContent = '图片加载失败';
    img.parentNode.appendChild(errorDiv);
}

function handleVideoError(video) {
    console.error('Video failed to load:', video.querySelector('source')?.src);
    video.style.display = 'none';
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message';
    errorDiv.textContent = '视频加载失败';
    video.parentNode.appendChild(errorDiv);
}

// 分页功能
function renderPagination(total, current, perPage) {
    const totalPages = Math.ceil(total / perPage);
    const pagination = document.getElementById('pagination');
    
    if (totalPages <= 1) {
        pagination.style.display = 'none';
        return;
    }
    
    pagination.style.display = 'flex';
    pagination.innerHTML = `
        <button onclick="changePage(1)" ${current === 1 ? 'disabled' : ''}>首页</button>
        <button onclick="changePage(${current - 1})" ${current === 1 ? 'disabled' : ''}>上一页</button>
        <span class="page-info">第 ${current} 页，共 ${totalPages} 页</span>
        <button onclick="changePage(${current + 1})" ${current === totalPages ? 'disabled' : ''}>下一页</button>
        <button onclick="changePage(${totalPages})" ${current === totalPages ? 'disabled' : ''}>末页</button>
    `;
}

function changePage(page) {
    currentPage = page;
    fetchMessages();
    window.scrollTo(0, 0);
}

// 发送消息
async function sendMessage() {
    const chatId = document.getElementById('chatId').value.trim();
    const messageContent = document.getElementById('messageContent').value.trim();
    const sendButton = document.querySelector('.send-button');
    const successMessage = document.getElementById('successMessage');
    
    if (!chatId || !messageContent) {
        alert('请填写聊天 ID 和消息内容');
        return;
    }
    
    sendButton.textContent = '发送中...';
    sendButton.disabled = true;
    
    try {
        const response = await fetch('/send_message', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                chat_id: chatId,
                message: messageContent
            })
        });
        
        const result = await response.json();
        
        if (response.ok && result.status === 'success') {
            successMessage.textContent = '消息发送成功！';
            successMessage.style.display = 'block';
            document.getElementById('messageContent').value = '';
            
            setTimeout(() => {
                successMessage.style.display = 'none';
            }, 3000);
            
            fetchMessages();
        } else {
            throw new Error(result.message || '发送失败');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('发送消息时出错：' + error.message);
    } finally {
        sendButton.textContent = '发送消息';
        sendButton.disabled = false;
    }
}

// 获取消息列表
async function fetchMessages() {
    const messagesContainer = document.getElementById('messages');
    messagesContainer.innerHTML = '<div class="loading">加载消息中...</div>';

    try {
        const queryParams = new URLSearchParams({
            page: currentPage,
            chat_type: currentFilters.chatType,
            message_type: currentFilters.messageType
        });

        const response = await fetch(`/messages?${queryParams}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        messagesContainer.innerHTML = '';

        if (data.messages && data.messages.length > 0) {
            data.messages.forEach(msg => {
                const messageElement = createMessageElement(msg);
                messagesContainer.appendChild(messageElement);
            });
            renderPagination(data.total, data.page, data.per_page);
        } else {
            messagesContainer.innerHTML = '<div class="no-messages">暂无消息</div>';
        }
    } catch (error) {
        console.error('Error fetching messages:', error);
        messagesContainer.innerHTML = `
            <div class="error-container">
                <div class="error-message">加载消息时出错：${error.message}</div>
                <button onclick="fetchMessages()" class="retry-button">重试</button>
            </div>
        `;
    }
}

// 自动刷新设置
function setupAutoRefresh() {
    const autoRefreshCheckbox = document.getElementById('autoRefresh');
    
    function updateAutoRefresh() {
        if (autoRefreshCheckbox.checked) {
            autoRefreshInterval = setInterval(fetchMessages, 5000);
        } else {
            clearInterval(autoRefreshInterval);
        }
    }
    
    autoRefreshCheckbox.addEventListener('change', updateAutoRefresh);
    updateAutoRefresh();
}

// 更新过滤器
function updateFilters() {
    const chatType = document.getElementById('chatType').value;
    const messageType = document.getElementById('messageType').value;
    
    currentFilters = {
        chatType,
        messageType
    };
    
    currentPage = 1;
    fetchMessages();
}

// 页面初始化
document.addEventListener('DOMContentLoaded', () => {
    fetchMessages();
    setupAutoRefresh();
});