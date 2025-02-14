// 定义图标组件
function ShieldLockIcon() {
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
    }),
    React.createElement('path', {
      key: 'lock',
      d: 'M8 11h8v4H8z'
    }),
    React.createElement('path', {
      key: 'keyhole',
      d: 'M12 13v2'
    })
  ]);
}

// 创建白名单组件
function WhitelistPanel({ chatId, adminId  }) {
  const [whitelist, setWhitelist] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [newUser, setNewUser] = useState({
    user_id: '',
    note: ''
  });

  // 获取白名单
  const fetchWhitelist = async () => {
    if (!chatId) return;
    
    try {
      setLoading(true);
      const response = await fetch(`/spam_filter/whitelist?chat_id=${chatId}`);
      const data = await response.json();
      
      if (data.status === 'success') {
        setWhitelist(data.whitelist);
        setError(null);
      } else {
        throw new Error(data.message || '获取白名单失败');
      }
    } catch (error) {
      setError('获取白名单失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  // 添加用户到白名单
  const addToWhitelist = async () => {
    if (!chatId || !newUser.user_id) return;
    
    try {
      setLoading(true);
      const response = await fetch('/spam_filter/whitelist', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          chat_id: chatId,
          user_id: parseInt(newUser.user_id),
          added_by: adminId,  // 使用传入的 adminId
          note: newUser.note
        })
      });
      
      const data = await response.json();
      if (data.status === 'success') {
        setNewUser({ user_id: '', note: '' });
        await fetchWhitelist();
        setError(null);
      } else {
        throw new Error(data.message || '添加失败');
      }
    } catch (error) {
      setError('添加失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  // 从白名单移除用户
  const removeFromWhitelist = async (userId) => {
    if (!chatId || !userId) return;
    
    try {
      setLoading(true);
      const response = await fetch('/spam_filter/whitelist', {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          chat_id: chatId,
          user_id: userId
        })
      });
      
      const data = await response.json();
      if (data.status === 'success') {
        await fetchWhitelist();
        setError(null);
      } else {
        throw new Error(data.message || '移除失败');
      }
    } catch (error) {
      setError('移除失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  // 在组件加载和chatId变化时获取白名单
  useEffect(() => {
    if (chatId) {
      fetchWhitelist();
    }
  }, [chatId]);

  // 格式化时间显示
  const formatDateTime = (dateTimeStr) => {
    if (!dateTimeStr) return '';
    try {
      const date = new Date(dateTimeStr);
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
      return dateTimeStr;
    }
  };

  return React.createElement('div', { className: 'mt-4 space-y-4' }, [
    // 标题
    React.createElement('h4', {
      key: 'title',
      className: 'text-lg font-medium'
    }, '白名单管理'),

    // 添加用户表单
    React.createElement('div', {
      key: 'add-form',
      className: 'space-y-3 bg-gray-50 p-4 rounded'
    }, [
      React.createElement('div', {
        className: 'flex flex-col gap-2'
      }, [
        React.createElement('label', {
          className: 'text-sm font-medium'
        }, '用户ID'),
        React.createElement('input', {
          type: 'text',
          value: newUser.user_id,
          onChange: (e) => setNewUser(prev => ({ ...prev, user_id: e.target.value })),
          placeholder: '输入用户ID',
          className: 'p-2 border rounded'
        })
      ]),
      React.createElement('div', {
        className: 'flex flex-col gap-2'
      }, [
        React.createElement('label', {
          className: 'text-sm font-medium'
        }, '备注（可选）'),
        React.createElement('input', {
          type: 'text',
          value: newUser.note,
          onChange: (e) => setNewUser(prev => ({ ...prev, note: e.target.value })),
          placeholder: '添加备注',
          className: 'p-2 border rounded'
        })
      ]),
      React.createElement('button', {
        onClick: addToWhitelist,
        disabled: loading || !newUser.user_id,
        className: 'w-full p-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400'
      }, loading ? '添加中...' : '添加到白名单')
    ]),

    // 错误提示
    error && React.createElement('div', {
      key: 'error',
      className: 'p-2 bg-red-100 text-red-800 rounded'
    }, error),

    // 白名单列表
    React.createElement('div', {
      key: 'whitelist',
      className: 'space-y-2'
    }, [
      whitelist.length === 0 
        ? React.createElement('div', {
            className: 'text-center text-gray-500 py-4'
          }, '暂无白名单用户')
        : whitelist.map(user => 
            React.createElement('div', {
              key: user.user_id,
              className: 'flex items-center justify-between p-3 bg-gray-50 rounded'
            }, [
              React.createElement('div', {
                className: 'space-y-1'
              }, [
                React.createElement('div', {
                  className: 'font-medium'
                }, [
                  user.full_name || `用户 ${user.user_id}`,
                  user.username && React.createElement('span', {
                    className: 'text-gray-500 text-sm ml-2'
                  }, `@${user.username}`)
                ]),
                React.createElement('div', {
                  className: 'text-sm text-gray-500'
                }, [
                  `ID: ${user.user_id}`,
                  user.note && React.createElement('span', {
                    className: 'ml-2'
                  }, `· ${user.note}`)
                ]),
                React.createElement('div', {
                  className: 'text-xs text-gray-400'
                }, `添加时间: ${formatDateTime(user.added_at)}`)
              ]),
              React.createElement('button', {
                onClick: () => removeFromWhitelist(user.user_id),
                disabled: loading,
                className: 'p-1 text-red-600 hover:text-red-800 disabled:text-gray-400'
              }, '移除')
            ])
          )
    ])
  ]);
}

function SpamFilterPanel() {
  const [selectedGroup, setSelectedGroup] = useState('');
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [settings, setSettings] = useState({
    enabled: false,
    rules: []
  });
  const [newRule, setNewRule] = useState({
    type: 'keyword',
    content: '',
    action: 'delete'
  });

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

  // 获取垃圾信息过滤设置
  const fetchSettings = async (chatId) => {
    try {
      setLoading(true);
      const response = await fetch(`/spam_filter/settings?chat_id=${chatId}`);
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

  // 保存设置
  const saveSettings = async () => {
    try {
      setLoading(true);
      const response = await fetch('/spam_filter/settings', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          chat_id: selectedGroup,
          enabled: settings.enabled,
          rules: settings.rules
        })
      });
      
      const data = await response.json();
      if (data.status === 'success') {
        setError(null);
        // 重新加载设置
        fetchSettings(selectedGroup);
      } else {
        throw new Error(data.message || '保存设置失败');
      }
    } catch (error) {
      setError('保存设置失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  // 添加新规则
  const addRule = () => {
    if (!newRule.content.trim()) {
      setError('规则内容不能为空');
      return;
    }
    
    setSettings(prev => ({
      ...prev,
      rules: [...prev.rules, { ...newRule, id: Date.now() }]
    }));
    
    setNewRule({
      type: 'keyword',
      content: '',
      action: 'delete'
    });
  };

  // 删除规则
  const deleteRule = (ruleId) => {
    setSettings(prev => ({
      ...prev,
      rules: prev.rules.filter(rule => rule.id !== ruleId)
    }));
  };

  // 在组件加载时获取群组列表
  useEffect(() => {
    fetchGroups();
  }, []);

  // 当选择的群组变化时，获取该群组的设置
  useEffect(() => {
    if (selectedGroup) {
      fetchSettings(selectedGroup);
    }
  }, [selectedGroup]);

  return React.createElement('div', {
    className: 'mt-6 border-t pt-4'
  }, [
    // 标题
    React.createElement('h3', {
      key: 'title',
      className: 'text-lg font-medium mb-4 flex items-center gap-2'
    }, [
      React.createElement(ShieldLockIcon),
      '垃圾信息过滤'
    ]),

    // 群组选择器
    React.createElement('div', {
      key: 'group-select',
      className: 'mb-4'
    }, 
      React.createElement('select', {
        className: 'w-full p-2 border rounded',
        value: selectedGroup,
        onChange: (e) => setSelectedGroup(e.target.value)
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

    // 功能启用开关
    selectedGroup && React.createElement('div', {
      key: 'enable-switch',
      className: 'mb-4 flex items-center gap-2'
    }, [
      React.createElement('input', {
        type: 'checkbox',
        id: 'spamFilterEnabled',
        checked: settings.enabled,
        onChange: (e) => setSettings(prev => ({
          ...prev,
          enabled: e.target.checked
        })),
        className: 'h-4 w-4'
      }),
      React.createElement('label', {
        htmlFor: 'spamFilterEnabled',
        className: 'text-sm font-medium'
      }, '启用垃圾信息过滤')
    ]),

    // 规则添加表单
    selectedGroup && settings.enabled && React.createElement('div', {
      key: 'add-rule-form',
      className: 'mb-4 p-4 bg-gray-50 rounded'
    }, [
      React.createElement('div', {
        className: 'grid grid-cols-1 md:grid-cols-3 gap-4'
      }, [
        // 规则类型选择
        React.createElement('div', {
          key: 'rule-type',
          className: 'flex flex-col gap-2'
        }, [
          React.createElement('label', {
            className: 'text-sm font-medium'
          }, '规则类型'),
          React.createElement('select', {
            value: newRule.type,
            onChange: (e) => setNewRule(prev => ({
              ...prev,
              type: e.target.value
            })),
            className: 'p-2 border rounded'
          }, [
            React.createElement('option', { value: 'keyword' }, '关键词'),
            React.createElement('option', { value: 'url' }, '网址链接'),
            React.createElement('option', { value: 'regex' }, '正则表达式')
          ])
        ]),
        
        // 规则内容输入
        React.createElement('div', {
          key: 'rule-content',
          className: 'flex flex-col gap-2'
        }, [
          React.createElement('label', {
            className: 'text-sm font-medium'
          }, '规则内容'),
          React.createElement('input', {
            type: 'text',
            value: newRule.content,
            onChange: (e) => setNewRule(prev => ({
              ...prev,
              content: e.target.value
            })),
            placeholder: newRule.type === 'keyword' ? '输入关键词' :
                        newRule.type === 'url' ? '输入URL关键词' :
                        '输入正则表达式',
            className: 'p-2 border rounded'
          })
        ]),
        
        // 动作选择
        React.createElement('div', {
          key: 'rule-action',
          className: 'flex flex-col gap-2'
        }, [
          React.createElement('label', {
            className: 'text-sm font-medium'
          }, '执行动作'),
          React.createElement('select', {
            value: newRule.action,
            onChange: (e) => setNewRule(prev => ({
              ...prev,
              action: e.target.value
            })),
            className: 'p-2 border rounded'
          }, [
            React.createElement('option', { value: 'delete' }, '删除消息'),
            React.createElement('option', { value: 'warn' }, '警告用户'),
            React.createElement('option', { value: 'mute' }, '禁言用户')
          ])
        ])
      ]),
      
      // 添加规则按钮
      React.createElement('button', {
        onClick: addRule,
        className: 'mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700',
        disabled: !newRule.content.trim()
      }, '添加规则')
    ]),

    // 现有规则列表
    selectedGroup && settings.enabled && React.createElement('div', {
      key: 'rules-list',
      className: 'space-y-2'
    }, [
      React.createElement('h4', {
        className: 'font-medium mb-2'
      }, '现有规则'),
      settings.rules.length === 0 
        ? React.createElement('p', {
            className: 'text-gray-500 text-center py-4'
          }, '暂无规则')
        : settings.rules.map(rule => 
            React.createElement('div', {
              key: rule.id,
              className: 'flex items-center justify-between p-3 bg-gray-50 rounded'
            }, [
              React.createElement('div', {
                className: 'flex-1'
              }, [
                React.createElement('div', {
                  className: 'font-medium'
                }, `${
                  rule.type === 'keyword' ? '关键词' :
                  rule.type === 'url' ? '网址链接' : '正则表达式'
                }: ${rule.content}`),
                React.createElement('div', {
                  className: 'text-sm text-gray-500'
                }, `动作: ${
                  rule.action === 'delete' ? '删除消息' :
                  rule.action === 'warn' ? '警告用户' : '禁言用户'
                }`)
              ]),
              React.createElement('button', {
                onClick: () => deleteRule(rule.id),
                className: 'ml-2 p-1 text-red-600 hover:text-red-800'
              }, '删除')
            ])
          )
    ]),

    // 保存按钮
    selectedGroup && settings.enabled && React.createElement('button', {
      key: 'save-button',
      onClick: saveSettings,
      disabled: loading,
      className: 'mt-4 w-full p-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:bg-gray-400'
    }, loading ? '保存中...' : '保存设置'),

    // 添加白名单面板
    selectedGroup && settings.enabled && React.createElement('div', {
      key: 'whitelist',
      className: 'mt-6 border-t pt-4'
    }, 
      React.createElement(WhitelistPanel, {
        chatId: selectedGroup,
        adminId: window.APP_CONFIG.adminId
      })
    ),

    // 错误提示
    error && React.createElement('div', {
      key: 'error',
      className: 'mt-4 p-2 bg-red-100 text-red-800 rounded'
    }, error)
  ]);
}

// 导出组件
window.WhitelistPanel = WhitelistPanel;
window.SpamFilterPanel = SpamFilterPanel;