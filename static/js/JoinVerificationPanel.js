// 定义图标组件
function ShieldIcon() {
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
    React.createElement('path', { 
      key: 'shield',
      d: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z' 
    })
  ]);
}

function UserCheckIcon() {
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
    React.createElement('path', { 
      key: 'user',
      d: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2' 
    }),
    React.createElement('circle', { 
      key: 'circle',
      cx: '9',
      cy: '7',
      r: '4'
    }),
    React.createElement('polyline', { 
      key: 'check',
      points: '16 11 18 13 22 9' 
    })
  ]);
}

function JoinVerificationPanel() {
  const [settings, setSettings] = useState({
    enabled: false,
    verify_type: 'question',
    question: '',
    answer: '',
    welcome_message: '',
    timeout: 300
  });
  const [pendingMembers, setPendingMembers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState('');
  const [selectedChatId, setSelectedChatId] = useState('');
  const [groups, setGroups] = useState([]);

  // 获取所有群组
  const fetchGroups = async () => {
    try {
      const response = await fetch('/api/groups');
      if (!response.ok) throw new Error('Failed to fetch groups');
      const data = await response.json();
      if (data.status === 'success') {
        setGroups(data.groups);
      }
    } catch (err) {
      setError('获取群组列表失败');
    }
  };

  // 在组件加载时获取群组列表
  useEffect(() => {
    fetchGroups();
  }, []);

  // 格式化时间显示
  const formatDateTime = (dateTimeStr) => {
    if (!dateTimeStr) return '';
    try {
      const date = new Date(dateTimeStr.replace(' ', 'T') + '+08:00');
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
  };

  // 获取设置
  const fetchSettings = async (chatId) => {
    try {
      setLoading(true);
      const response = await fetch(`/join_settings?chat_id=${chatId}`);
      const data = await response.json();
      
      if (data.status === 'success') {
        setSettings(data.settings);
        setError(null);
      } else {
        throw new Error(data.message || '获取设置失败');
      }
    } catch (error) {
      setError('获取设置失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  // 获取待验证用户列表
  const fetchPendingMembers = async (chatId) => {
    try {
      setLoading(true);
      const response = await fetch(`/pending_members?chat_id=${chatId}`);
      const data = await response.json();
      
      if (data.status === 'success') {
        setPendingMembers(data.members);
        setError(null);
      } else {
        throw new Error(data.message || '获取待验证用户失败');
      }
    } catch (error) {
      setError('获取待验证用户失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  // 保存设置
  const saveSettings = async () => {
    try {
      setLoading(true);
      const response = await fetch('/join_settings', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          chat_id: selectedChatId,
          ...settings
        })
      });
      
      const data = await response.json();
      if (data.status === 'success') {
        setStatus('设置已保存');
        setError(null);
      } else {
        throw new Error(data.message || '保存设置失败');
      }
    } catch (error) {
      setError('保存设置失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  // 处理验证结果
  const handleVerification = async (userId, approved) => {
    try {
      setLoading(true);
      const response = await fetch('/verify_member', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          chat_id: selectedChatId,
          user_id: userId,
          approved
        })
      });
      
      const data = await response.json();
      if (data.status === 'success') {
        setStatus('验证处理完成');
        // 刷新待验证用户列表
        fetchPendingMembers(selectedChatId);
        setError(null);
      } else {
        throw new Error(data.message || '处理验证失败');
      }
    } catch (error) {
      setError('处理验证失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  // 监听选择的群组变化
  useEffect(() => {
    if (selectedChatId) {
      fetchSettings(selectedChatId);
      fetchPendingMembers(selectedChatId);
    }
  }, [selectedChatId]);

  // 定期刷新待验证用户列表
  useEffect(() => {
    if (selectedChatId) {
      // 每30秒刷新一次
      const interval = setInterval(() => {
        fetchPendingMembers(selectedChatId);
      }, 30000);
      
      return () => clearInterval(interval);
    }
  }, [selectedChatId]);

  return React.createElement('div', { 
    className: 'mt-6 border-t pt-4'
  }, [
    // 标题
    React.createElement('h3', {
      key: 'title',
      className: 'text-lg font-medium mb-4 flex items-center gap-2'
    }, [
      React.createElement(ShieldIcon, { key: 'icon' }),
      '入群验证设置'
    ]),

    // 新增: 群组选择器
    React.createElement('div', {
      key: 'group-select',
      className: 'mb-4'
    }, 
      React.createElement('select', {
        className: 'w-full p-2 border rounded',
        value: selectedChatId,
        onChange: (e) => setSelectedChatId(e.target.value)
      }, [
        React.createElement('option', { value: '' }, '请选择群组'),
        ...groups.map(group => 
          React.createElement('option', {
            key: group.id,
            value: group.id
          }, group.title)
        )
      ])
    ),

    // 设置表单
    React.createElement('div', {
      key: 'settings',
      className: 'space-y-4'
    }, [
      // 启用开关
      React.createElement('div', {
        className: 'flex items-center gap-2'
      }, [
        React.createElement('input', {
          type: 'checkbox',
          id: 'verifyEnabled',
          checked: settings.enabled,
          onChange: (e) => setSettings({
            ...settings,
            enabled: e.target.checked
          }),
          className: 'h-4 w-4'
        }),
        React.createElement('label', {
          htmlFor: 'verifyEnabled',
          className: 'text-sm font-medium'
        }, '启用入群验证')
      ]),

      // 其他设置（仅在选择了群组和启用验证时显示）
      selectedChatId && React.createElement('div', {
        className: 'space-y-4'
      }, [
        React.createElement('div', {
          className: 'flex flex-col gap-2'
        }, [
          React.createElement('label', {
            className: 'text-sm font-medium'
          }, '验证方式'),
          React.createElement('select', {
            value: settings.verify_type,
            onChange: (e) => setSettings({
              ...settings,
              verify_type: e.target.value
            }),
            className: 'w-full p-2 border rounded'
          }, [
            React.createElement('option', {
              value: 'question'
            }, '入群问答'),
            React.createElement('option', {
              value: 'manual'
            }, '管理员审核')
          ])
        ]),

        // 问答设置
        settings.verify_type === 'question' && React.createElement('div', {
          className: 'space-y-4'
        }, [
          React.createElement('div', {
            className: 'flex flex-col gap-2'
          }, [
            React.createElement('label', {
              className: 'text-sm font-medium'
            }, '验证问题'),
            React.createElement('input', {
              type: 'text',
              value: settings.question,
              onChange: (e) => setSettings({
                ...settings,
                question: e.target.value
              }),
              className: 'w-full p-2 border rounded'
            })
          ]),
          React.createElement('div', {
            className: 'flex flex-col gap-2'
          }, [
            React.createElement('label', {
              className: 'text-sm font-medium'
            }, '正确答案'),
            React.createElement('input', {
              type: 'text',
              value: settings.answer,
              onChange: (e) => setSettings({
                ...settings,
                answer: e.target.value
              }),
              className: 'w-full p-2 border rounded'
            })
          ])
        ]),

        // 欢迎消息
        React.createElement('div', {
          className: 'flex flex-col gap-2'
        }, [
          React.createElement('label', {
            className: 'text-sm font-medium'
          }, '欢迎消息（可选）'),
          React.createElement('textarea', {
            value: settings.welcome_message,
            onChange: (e) => setSettings({
              ...settings,
              welcome_message: e.target.value
            }),
            placeholder: '验证通过后发送的欢迎消息，支持HTML格式',
            className: 'w-full p-2 border rounded h-24'
          })
        ]),

        // 验证时限
        React.createElement('div', {
          className: 'flex flex-col gap-2'
        }, [
          React.createElement('label', {
            className: 'text-sm font-medium'
          }, '验证时限（秒）'),
          React.createElement('input', {
            type: 'number',
            value: settings.timeout,
            onChange: (e) => setSettings({
              ...settings,
              timeout: parseInt(e.target.value) || 300
            }),
            min: 60,
            max: 3600,
            className: 'w-full p-2 border rounded'
          })
        ]),

        // 保存按钮也要始终显示
        React.createElement('button', {
          onClick: saveSettings,
          disabled: loading,
          className: 'w-full p-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400'
        }, loading ? '保存中...' : '保存设置')
      ]),

      // 待验证用户列表（仅在选择了群组和启用验证时显示）
      selectedChatId && settings.enabled && React.createElement('div', {
        key: 'pending-members',
        className: 'mt-6 space-y-4'
      }, [
        React.createElement('h4', {
          className: 'text-lg font-medium flex items-center gap-2'
        }, [
          React.createElement(UserCheckIcon),
          '待验证用户'
        ]),
        pendingMembers.length === 0 
          ? React.createElement('div', {
              className: 'text-gray-500 text-center py-4'
            }, '暂无待验证用户') 
          : React.createElement('div', {
              className: 'space-y-2'
            }, pendingMembers.map(member => 
              React.createElement('div', {
                key: member.user_id,
                className: 'border rounded p-3 bg-gray-50'
              }, [
                React.createElement('div', {
                  className: 'flex items-center justify-between'
                }, [
                  React.createElement('div', {
                    className: 'space-y-1'
                  }, [
                    React.createElement('div', {
                      className: 'font-medium'
                    }, member.full_name),
                    React.createElement('div', {
                      className: 'text-sm text-gray-500'
                    }, [
                      member.username && `@${member.username}`,
                      React.createElement('span', {
                        className: 'mx-1'
                      }, '•'),
                      `ID: ${member.user_id}`
                    ]),
                    React.createElement('div', {
                      className: 'text-xs text-gray-500'
                    }, `加入时间: ${formatDateTime(member.join_time)}`),
                    React.createElement('div', {
                      className: 'text-xs text-gray-500'
                    }, `验证期限: ${formatDateTime(member.verify_deadline)}`)
                  ]),
                  React.createElement('div', {
                    className: 'flex gap-2'
                  }, [
                    React.createElement('button', {
                      onClick: () => handleVerification(member.user_id, true),
                      disabled: loading,
                      className: 'px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 disabled:bg-gray-400'
                    }, '通过'),
                    React.createElement('button', {
                      onClick: () => handleVerification(member.user_id, false),
                      disabled: loading,
                      className: 'px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700 disabled:bg-gray-400'
                    }, '拒绝')
                  ])
                ])
              ])
            ))
      ]),

      // 错误提示
      error && React.createElement('div', {
        key: 'error',
        className: 'mt-4 p-2 bg-red-100 text-red-800 rounded'
      }, error),

      // 状态提示
      status && React.createElement('div', {
        key: 'status',
        className: 'mt-4 p-2 bg-green-100 text-green-800 rounded'
      }, status)
    ])
  ]);
}

// 导出组件
window.JoinVerificationPanel = JoinVerificationPanel;