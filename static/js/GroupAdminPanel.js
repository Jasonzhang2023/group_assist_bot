// 定义 React Hooks
const { useState, useEffect } = React;

// 图标组件
function ClockIcon() {
  return React.createElement('svg', {
    xmlns: 'http://www.w3.org/2000/svg',
    width: '24',
    height: '24',
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: '2',
    strokeLinecap: 'round',
    strokeLinejoin: 'round'
  }, [
    React.createElement('circle', { key: 'circle', cx: '12', cy: '12', r: '10' }),
    React.createElement('polyline', { key: 'hands', points: '12 6 12 12 16 14' })
  ]);
}

function BanIcon() {
  return React.createElement('svg', {
    xmlns: 'http://www.w3.org/2000/svg',
    width: '24',
    height: '24',
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: '2',
    strokeLinecap: 'round',
    strokeLinejoin: 'round'
  }, [
    React.createElement('circle', { key: 'circle', cx: '12', cy: '12', r: '10' }),
    React.createElement('line', { key: 'line', x1: '4.93', y1: '4.93', x2: '19.07', y2: '19.07' })
  ]);
}

function AlertCircleIcon() {
  return React.createElement('svg', {
    xmlns: 'http://www.w3.org/2000/svg',
    width: '24',
    height: '24',
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: '2',
    strokeLinecap: 'round',
    strokeLinejoin: 'round'
  }, [
    React.createElement('circle', { key: 'circle', cx: '12', cy: '12', r: '10' }),
    React.createElement('line', { key: 'line1', x1: '12', y1: '8', x2: '12', y2: '12' }),
    React.createElement('line', { key: 'line2', x1: '12', y1: '16', x2: '12.01', y2: '16' })
  ]);
}

// 简化版卡片组件
function Card({ children, className }) {
  return React.createElement('div', { 
    className: `bg-white rounded-lg shadow-md ${className || ''}`
  }, children);
}

function CardHeader({ children }) {
  return React.createElement('div', { 
    className: 'p-4 border-b'
  }, children);
}

function CardContent({ children }) {
  return React.createElement('div', { 
    className: 'p-4'
  }, children);
}

function CardTitle({ children, className }) {
  return React.createElement('h2', { 
    className: `text-lg font-bold ${className || ''}`
  }, children);
}

// 自动禁言状态面板组件
function AutoMuteStatusPanel() {
  const [settings, setSettings] = useState([]);
  const [error, setError] = useState(null);

  // 格式化星期显示
  const formatDays = (days) => {
    const dayNames = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
    return days.map(day => dayNames[day]).join('、');
  };

  const fetchSettings = async () => {
    try {
      const response = await fetch('/auto_mute/list');
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      if (data.status === 'success') {
        console.log('成功获取设置:', data.settings);
        setSettings(data.settings || []);
        setError(null);
      } else {
        throw new Error(data.message || '获取设置失败');
      }
    } catch (error) {
      console.error('获取自动禁言设置失败:', error);
      setError('获取自动禁言设置失败: ' + error.message);
      setSettings([]);
    }
  };

  // 添加 useEffect 以定期获取设置
  useEffect(() => {
    console.log('AutoMuteStatusPanel mounted');
    fetchSettings();
    const interval = setInterval(fetchSettings, 10000);
    return () => clearInterval(interval);
  }, []);

  // 格式化时间显示
  function formatDateTime(dateTimeStr) {
    if (!dateTimeStr) return '';
    try {
      // 解析日期时间字符串
      const date = new Date(dateTimeStr.replace(' ', 'T') + '+16:00');
      
      // 格式化为北京时间
      return date.toLocaleString('zh-CN', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      });
    } catch (e) {
      console.error('时间格式化错误:', e);
      return dateTimeStr;
    }
  }

  // 修改 handleDelete 函数
  const handleDelete = async (chatId) => {
    if (!confirm('确定要删除这个自动禁言设置吗？')) {
      return;
    }
    try {
      const response = await fetch('/auto_mute/delete', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          chat_id: chatId
        })
      });

      if (!response.ok) {
        throw new Error('删除失败');
      }

      // 删除成功后刷新列表
      fetchSettings();
    } catch (error) {
      setError('删除设置失败: ' + error.message);
    }
  };

  // 编辑按钮点击处理
  const handleEdit = (chatId) => {
    // 找到对应的设置并填充到主面板的表单中
    const setting = settings.find(s => s.chat_id === chatId);
    if (setting) {
      // 发送自定义事件通知主面板
      const event = new CustomEvent('editAutoMuteSetting', {
        detail: {
          chatId: setting.chat_id,
          startTime: setting.start_time,
          endTime: setting.end_time,
          daysOfWeek: setting.days_of_week,
          muteLevel: setting.mute_level
        }
      });
      window.dispatchEvent(event);
    }
  };

  // 渲染组件
  return React.createElement(Card, {
    className: 'w-full shadow-lg'
  }, [
    React.createElement(CardHeader, { key: 'header' }, 
      React.createElement(CardTitle, { className: 'text-lg font-bold flex items-center gap-2' }, [
        React.createElement(ClockIcon, { key: 'icon' }),
        '自动禁言状态'
      ])
    ),
    React.createElement(CardContent, { key: 'content' },
      error ? React.createElement('div', { className: 'text-red-500 p-2' }, error) :
      settings.length === 0 ? React.createElement('div', { className: 'text-gray-500 p-2' }, '暂无自动禁言设置') :
      React.createElement('div', { className: 'space-y-4' },
        settings.map((setting) => 
          React.createElement('div', {
            key: setting.chat_id,
            className: 'border rounded p-3 bg-gray-50'
          }, [
            React.createElement('div', { key: 'content', className: 'text-sm space-y-1' }, [
              React.createElement('div', { key: 'id', className: 'font-medium' }, `群组ID: ${setting.chat_id}`),
              React.createElement('div', { key: 'time' }, `时间: ${setting.start_time} - ${setting.end_time}`),
              React.createElement('div', { key: 'days' }, `生效日期: ${formatDays(setting.days_of_week)}`),
              React.createElement('div', { key: 'level' }, `禁言级别: ${setting.mute_level === 'strict' ? '严格' : '轻度'}`),
              React.createElement('div', { 
                key: 'status',
                className: `text-sm ${setting.enabled ? 'text-green-600' : 'text-red-600'}`
              }, `状态: ${setting.enabled ? '已启用' : '已禁用'}`),
              React.createElement('div', { 
                key: 'update',
                className: 'text-xs text-gray-500'
              }, `更新时间: ${formatDateTime(setting.updated_at)}`),
              // 添加操作按钮
              React.createElement('div', {
                key: 'actions',
                className: 'mt-2 flex gap-2'
              }, [
                React.createElement('button', {
                  key: 'edit-btn',
                  className: 'px-2 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600',
                  onClick: () => handleEdit(setting.chat_id)
                }, '编辑'),
                React.createElement('button', {
                  key: 'delete-btn',
                  className: 'px-2 py-1 text-xs bg-red-500 text-white rounded hover:bg-red-600',
                  onClick: () => handleDelete(setting.chat_id)
                }, '删除')
              ])
            ])
          ])
        )
      )
    )
  ]);
}

function GroupAdminPanel() {
  const [chatId, setChatId] = useState('');
  const [userId, setUserId] = useState('');
  const [banDuration, setBanDuration] = useState('');
  const [userMuteDuration, setUserMuteDuration] = useState('');
  const [groupMuteDuration, setGroupMuteDuration] = useState('');
  const [muteLevel, setMuteLevel] = useState('strict');
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(false);
  const [autoMuteEnabled, setAutoMuteEnabled] = useState(false);
  const [autoMuteSettings, setAutoMuteSettings] = useState({
    startTime: '23:00',
    endTime: '06:00',
    daysOfWeek: [0, 1, 2, 3, 4, 5, 6],
    muteLevel: 'light'
  });
  const [autoMuteStatus, setAutoMuteStatus] = useState({});

  // 添加编辑事件监听
  useEffect(() => {
    function handleEditRequest(event) {
      if (event.detail) {
        const { chatId, startTime, endTime, daysOfWeek, muteLevel } = event.detail;
        setChatId(chatId.toString());
        setAutoMuteEnabled(true);
        setAutoMuteSettings({
          startTime,
          endTime,
          daysOfWeek,
          muteLevel
        });
        const settingsElement = document.querySelector('#auto-mute-settings');
        if (settingsElement) {
          settingsElement.scrollIntoView({ behavior: 'smooth' });
        }
      }
    }

    window.addEventListener('editAutoMuteSetting', handleEditRequest);
    return () => {
      window.removeEventListener('editAutoMuteSetting', handleEditRequest);
    };
  }, []);

  useEffect(() => {
    const checkExistingSettings = async () => {
      try {
        const response = await fetch(`/auto_mute/settings?chat_id=${chatId}`);
        const data = await response.json();
        if (data.status === 'success' && data.settings) {
          setAutoMuteEnabled(data.settings.enabled);
          setAutoMuteSettings({
            startTime: data.settings.start_time,
            endTime: data.settings.end_time,
            daysOfWeek: data.settings.days_of_week,
            muteLevel: data.settings.mute_level
          });
        }
      } catch (error) {
        console.error('Error fetching auto mute settings:', error);
      }
    };

    if (chatId) {
      checkExistingSettings();
    }
  }, [chatId]);

  useEffect(() => {
    function handleMuteRequest(event) {
      if (event.detail) {
        const { chatId, userId } = event.detail;
        setChatId(chatId);
        setUserId(userId);
        const panelElement = document.getElementById('groupAdminRoot');
        if (panelElement) {
          panelElement.scrollIntoView({ behavior: 'smooth' });
        }
      }
    }

    window.addEventListener('fillMuteForm', handleMuteRequest);
    return () => {
      window.removeEventListener('fillMuteForm', handleMuteRequest);
    };
  }, []);

  // 修改 handleAction 函数
  const handleAction = async (action, overrideData = {}) => {
    setLoading(true);
    setStatus('');
    
    try {
      const endpoint = action === 'ban' ? '/ban_user' :
                      action === 'unban' ? '/unban_user' :
                      action === 'mute' ? '/mute_user' :
                      action === 'unmute' ? '/unmute_user' :
                      action === 'muteAll' ? '/mute_all' : '/unmute_all';
      
      const data = {
        chat_id: chatId,
        ...(userId && { user_id: userId }),
        ...(action === 'ban' && banDuration && { duration: parseInt(banDuration) }),
        ...(action === 'mute' && userMuteDuration && { duration: parseInt(userMuteDuration) }),
        ...(action === 'muteAll' && {
          duration: groupMuteDuration ? parseInt(groupMuteDuration) : null,
          mute_level: overrideData.mute_level || muteLevel
        })
      };

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });

      const result = await response.json();
      
      if (response.ok) {
        setStatus(`操作成功: ${result.message}`);
        if (action === 'ban') setBanDuration('');
        if (action === 'mute') setUserMuteDuration('');
        if (action === 'muteAll') setGroupMuteDuration('');
      } else {
        setStatus(`操作失败: ${result.message}`);
      }
    } catch (error) {
      setStatus(`操作失败: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  return React.createElement('div', { className: 'space-y-4' }, [
    // 主布局容器
    React.createElement('div', { 
      key: 'main-container',
      className: 'flex gap-4 min-h-[calc(100vh-200px)]'
    }, [
      // 左侧面板：群组成员列表
      React.createElement('div', { 
        key: 'left-panel',
        className: 'w-1/4 min-w-[300px]'
      }, 
        React.createElement(window.GroupMembersPanel)
      ),

      // 中间面板：管理控制面板
      React.createElement(Card, {
        key: 'center-panel',
        className: 'flex-1'
      }, [
        React.createElement(CardHeader, { key: 'header' },
          React.createElement('div', {
            className: 'flex items-center gap-2 text-lg font-bold'
          }, [
            React.createElement(BanIcon, { key: 'icon' }),
            '群组管理面板'
          ])
        ),
        React.createElement(CardContent, { key: 'content' },
          React.createElement('div', { className: 'space-y-4' }, [
            // 群组ID输入
            React.createElement('div', { key: 'chat-id', className: 'flex flex-col gap-2' }, [
              React.createElement('label', { className: 'text-sm font-medium' }, '群组 ID'),
              React.createElement('input', {
                type: 'text',
                className: 'w-full p-2 border rounded',
                value: chatId,
                onChange: (e) => setChatId(e.target.value),
                placeholder: '输入群组 ID（例如：-100xxx）'
              })
            ]),
            
            // 用户ID输入
            React.createElement('div', { key: 'user-id', className: 'flex flex-col gap-2' }, [
              React.createElement('label', { className: 'text-sm font-medium' }, '用户 ID'),
              React.createElement('input', {
                type: 'text',
                className: 'w-full p-2 border rounded',
                value: userId,
                onChange: (e) => setUserId(e.target.value),
                placeholder: '输入用户 ID'
              })
            ]),

            // 时长输入区域
            React.createElement('div', { key: 'durations', className: 'grid grid-cols-1 md:grid-cols-2 gap-4' }, [
              React.createElement('div', { className: 'flex flex-col gap-2' }, [
                React.createElement('label', { className: 'text-sm font-medium' }, '封禁时长（秒）'),
                React.createElement('input', {
                  type: 'number',
                  className: 'w-full p-2 border rounded',
                  value: banDuration,
                  onChange: (e) => setBanDuration(e.target.value),
                  placeholder: '留空表示永久'
                })
              ]),
              React.createElement('div', { className: 'flex flex-col gap-2' }, [
                React.createElement('label', { className: 'text-sm font-medium' }, '用户禁言时长（秒）'),
                React.createElement('input', {
                  type: 'number',
                  className: 'w-full p-2 border rounded',
                  value: userMuteDuration,
                  onChange: (e) => setUserMuteDuration(e.target.value),
                  placeholder: '留空表示永久'
                })
              ])
            ]),

            // 操作按钮组
            React.createElement('div', { key: 'actions', className: 'grid grid-cols-2 md:grid-cols-4 gap-2' }, [
              React.createElement('button', {
                className: 'p-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:bg-gray-400',
                onClick: () => handleAction('ban'),
                disabled: loading || !chatId || !userId
              }, '封禁用户'),
              React.createElement('button', {
                className: 'p-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:bg-gray-400',
                onClick: () => handleAction('unban'),
                disabled: loading || !chatId || !userId
              }, '解除封禁'),
              React.createElement('button', {
                className: 'p-2 bg-yellow-600 text-white rounded hover:bg-yellow-700 disabled:bg-gray-400',
                onClick: () => handleAction('mute'),
                disabled: loading || !chatId || !userId
              }, '禁言用户'),
              React.createElement('button', {
                className: 'p-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400',
                onClick: () => handleAction('unmute'),
                disabled: loading || !chatId || !userId
              }, '解除禁言')
            ]),

            // 全群禁言控制
            React.createElement('div', { key: 'mute-all', className: 'mt-6 border-t pt-4 space-y-4' }, [
              React.createElement('h3', { 
                className: 'text-lg font-medium mb-4 flex items-center gap-2'
              }, [
                React.createElement(ClockIcon, { key: 'clock' }),
                '全群禁言控制'
              ]),
              React.createElement('div', { className: 'grid grid-cols-1 gap-4' }, [
                React.createElement('div', { className: 'flex flex-col gap-2' }, [
                  React.createElement('label', { className: 'text-sm font-medium' }, '禁言级别'),
                  React.createElement('select', {
                    className: 'w-full p-2 border rounded',
                    value: muteLevel,
                    onChange: (e) => setMuteLevel(e.target.value)
                  }, [
                    React.createElement('option', { value: 'strict' }, '严格禁言（禁止所有消息）'),
                    React.createElement('option', { value: 'light' }, '轻度禁言（仅允许文字消息）')
                  ])
                ]),
                React.createElement('div', { className: 'flex flex-col gap-2' }, [
                  React.createElement('label', { className: 'text-sm font-medium' }, '全群禁言时长（秒）'),
                  React.createElement('input', {
                    type: 'number',
                    className: 'w-full p-2 border rounded',
                    value: groupMuteDuration,
                    onChange: (e) => setGroupMuteDuration(e.target.value),
                    placeholder: '留空表示永久'
                  })
                ]),
                React.createElement('div', { className: 'flex gap-2' }, [
                  React.createElement('button', {
                    className: 'flex-1 p-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:bg-gray-400',
                    onClick: () => handleAction('muteAll'),
                    disabled: loading || !chatId
                  }, '开启全群禁言'),
                  React.createElement('button', {
                    className: 'flex-1 p-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:bg-gray-400',
                    onClick: () => handleAction('unmuteAll'),
                    disabled: loading || !chatId
                  }, '解除全群禁言')
                ])
              ])
            ]),

            // 自动禁言设置
            React.createElement('div', { 
              key: 'auto-mute',
              id: 'auto-mute-settings',
              className: 'mt-6 border-t pt-4'
            }, [
              React.createElement('h3', { 
                className: 'text-lg font-medium mb-4 flex items-center gap-2'
              }, [
                React.createElement(ClockIcon, { key: 'clock' }),
                '自动禁言设置'
              ]),
              
              // 启用开关和确认按钮
              React.createElement('div', { className: 'space-y-4 mb-4' }, [
                React.createElement('div', { className: 'flex items-center gap-2' }, [
                  React.createElement('input', {
                    type: 'checkbox',
                    id: 'autoMuteEnabled',
                    checked: autoMuteEnabled,
                    onChange: (e) => setAutoMuteEnabled(e.target.checked),
                    className: 'h-4 w-4'
                  }),
                  React.createElement('label', { 
                    htmlFor: 'autoMuteEnabled',
                    className: 'text-sm font-medium'
                  }, '启用自动禁言')
                ])
              ]),
              
              autoMuteEnabled && React.createElement('div', { className: 'space-y-4' }, [
                // 时间范围设置
                React.createElement('div', { className: 'grid grid-cols-2 gap-4' }, [
                  React.createElement('div', { className: 'flex flex-col gap-2' }, [
                    React.createElement('label', { className: 'text-sm font-medium' }, '开始时间'),
                    React.createElement('input', {
                      type: 'time',
                      value: autoMuteSettings.startTime,
                      onChange: (e) => setAutoMuteSettings({
                        ...autoMuteSettings,
                        startTime: e.target.value
                      }),
                      className: 'w-full p-2 border rounded'
                    })
                  ]),
                  React.createElement('div', { className: 'flex flex-col gap-2' }, [
                    React.createElement('label', { className: 'text-sm font-medium' }, '结束时间'),
                    React.createElement('input', {
                      type: 'time',
                      value: autoMuteSettings.endTime,
                      onChange: (e) => setAutoMuteSettings({
                        ...autoMuteSettings,
                        endTime: e.target.value
                      }),
                      className: 'w-full p-2 border rounded'
                    })
                  ])
                ]),
                
                // 禁言级别选择
                React.createElement('div', { className: 'flex flex-col gap-2' }, [
                  React.createElement('label', { className: 'text-sm font-medium' }, '自动禁言级别'),
                  React.createElement('select', {
                    value: autoMuteSettings.muteLevel,
                    onChange: (e) => setAutoMuteSettings({
                      ...autoMuteSettings,
                      muteLevel: e.target.value
                    }),
                    className: 'w-full p-2 border rounded'
                  }, [
                    React.createElement('option', { value: 'light' }, '轻度禁言（仅允许文字消息）'),
                    React.createElement('option', { value: 'strict' }, '严格禁言（禁止所有消息）')
                  ])
                ]),
                
                // 星期选择
                React.createElement('div', { className: 'flex flex-col gap-2' }, [
                  React.createElement('label', { className: 'text-sm font-medium' }, '生效日期'),
                  React.createElement('div', { className: 'flex flex-wrap gap-2' }, 
                    ['周日', '周一', '周二', '周三', '周四', '周五', '周六'].map((day, index) => 
                      React.createElement('label', { 
                        key: index,
                        className: 'flex items-center gap-1'
                      }, [
                        React.createElement('input', {
                          type: 'checkbox',
                          checked: autoMuteSettings.daysOfWeek.includes(index),
                          onChange: (e) => {
                            const newDays = e.target.checked
                              ? [...autoMuteSettings.daysOfWeek, index].sort()
                              : autoMuteSettings.daysOfWeek.filter(d => d !== index);
                            setAutoMuteSettings({
                              ...autoMuteSettings,
                              daysOfWeek: newDays
                            });
                          },
                          className: 'h-4 w-4'
                        }),
                        day
                      ])
                    )
                  )
                ]),
                
                // 确认按钮
                React.createElement('div', { className: 'flex justify-end' },
                  React.createElement('button', {
                    className: 'p-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:bg-gray-400',
                    onClick: async () => {
                      try {
                        setLoading(true);
                        // 保存自动禁言设置
                        const response = await fetch('/auto_mute/settings', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({
                            chat_id: parseInt(chatId),
                            enabled: true,
                            start_time: autoMuteSettings.startTime,
                            end_time: autoMuteSettings.endTime,
                            days_of_week: autoMuteSettings.daysOfWeek,
                            mute_level: autoMuteSettings.muteLevel
                          })
                        });
                        
                        const result = await response.json();
                        if (response.ok && result.status === 'success') {
                          // 发送确认消息到群组
                          const msgResponse = await fetch('/send_message', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                              chat_id: chatId,
                              message: `⚠️ 自动宵禁模式已开启\n\n🕒 禁言时间：${autoMuteSettings.startTime} - ${autoMuteSettings.endTime}\n📅 生效日期：${
                                autoMuteSettings.daysOfWeek.map(day => ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][day]).join('、')
                              }\n🔒 禁言级别：${autoMuteSettings.muteLevel === 'strict' ? '严格禁言（禁止所有消息）' : '轻度禁言（仅允许文字消息）'}`
                            })
                          });

                          if (msgResponse.ok) {
                            // 检查当前时间是否应该立即启动禁言
                            const now = new Date();
                            const currentTime = now.toLocaleTimeString('en-GB', { 
                              hour: '2-digit', 
                              minute: '2-digit',
                              hour12: false 
                            });
                            const currentDay = now.getDay();
                            
                            const startTime = autoMuteSettings.startTime;
                            const endTime = autoMuteSettings.endTime;
                            
                            const shouldBeMuted = (() => {
                              const current = currentTime.split(':').map(Number);
                              const start = startTime.split(':').map(Number);
                              const end = endTime.split(':').map(Number);
                              
                              const currentMinutes = current[0] * 60 + current[1];
                              const startMinutes = start[0] * 60 + start[1];
                              const endMinutes = end[0] * 60 + end[1];
                              
                              if (endMinutes < startMinutes) {
                                // 跨天情况
                                return currentMinutes >= startMinutes || currentMinutes < endMinutes;
                              } else {
                                // 同日情况
                                return currentMinutes >= startMinutes && currentMinutes < endMinutes;
                              }
                            })();
                            
                            const isInSelectedDays = autoMuteSettings.daysOfWeek.includes(currentDay);
                            
                            if (shouldBeMuted && isInSelectedDays) {
                              // 立即执行禁言
                              const muteResponse = await fetch('/mute_all', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                  chat_id: parseInt(chatId),
                                  mute_level: autoMuteSettings.muteLevel,
                                  is_auto_mute: true
                                })
                              });
                              
                              if (!muteResponse.ok) {
                                throw new Error('立即禁言失败');
                              }
                            }
                            
                            setStatus('自动禁言设置已保存并开启');
                            setAutoMuteStatus({ enabled: true });
                          } else {
                            throw new Error('发送通知消息失败');
                          }
                        } else {
                          throw new Error(result.message || '操作失败');
                        }
                      } catch (error) {
                        setStatus('设置失败: ' + error.message);
                        setAutoMuteEnabled(false);
                        setAutoMuteStatus({ enabled: false });
                      } finally {
                        setLoading(false);
                      }
                    },
                    disabled: loading || !chatId
                  }, '确认并开启')
                )
              ])
            ]),
            // 垃圾信息过滤设置
            React.createElement('div', { 
              key: 'spam-filter',
              className: 'mt-6 border-t pt-4'
            }, React.createElement(window.SpamFilterPanel)),

            // 入群验证设置
            React.createElement('div', { 
              key: 'join-verification',
              className: 'mt-6 border-t pt-4'
            }, React.createElement(window.JoinVerificationPanel)),

            // 状态消息
            status && React.createElement('div', { 
              key: 'status',
              className: `p-3 rounded flex items-center gap-2 ${
                status.includes('成功') ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
              }`
            }, [
              React.createElement(AlertCircleIcon, { key: 'alert' }),
              React.createElement('span', {}, status)
            ])
          ])
        )
      ]),

      // 右侧面板：自动禁言状态
      React.createElement('div', { 
        key: 'right-panel',
        className: 'w-72'
      }, 
        React.createElement(AutoMuteStatusPanel)
      )
    ])
  ]);
}

// 将组件暴露到全局作用域
window.GroupAdminPanel = GroupAdminPanel;

// 在页面加载完成后渲染组件
window.addEventListener('DOMContentLoaded', () => {
  const container = document.getElementById('groupAdminRoot');
  const root = ReactDOM.createRoot(container);
  root.render(React.createElement(GroupAdminPanel));
});