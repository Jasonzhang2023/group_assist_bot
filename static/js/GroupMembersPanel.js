function GroupMembersPanel() {
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [groups, setGroups] = useState([]);
  const [stats, setStats] = useState({
    totalMembers: 0,
    visibleMembers: 0,
    chatTitle: ''
  });

  // 获取所有群组
  const fetchGroups = async () => {
    try {
      const response = await fetch('/api/groups');
      if (!response.ok) throw new Error('Failed to fetch groups');
      const data = await response.json();
      setGroups(data.groups);
    } catch (err) {
      setError('Failed to load groups');
    }
  };

  // 获取群组成员
  const fetchMembers = async (groupId) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/group_members/${groupId}`);
      if (!response.ok) throw new Error('Failed to fetch members');
      const data = await response.json();
      setMembers(data.members);
      setSelectedGroup(groupId);
      setStats({
        totalMembers: data.total_members,
        visibleMembers: data.visible_members,
        chatTitle: data.chat_title
      });
    } catch (err) {
      setError('Failed to load members');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGroups();
  }, []);

  // 格式化最后活跃时间
  const formatLastActive = (timestamp) => {
    if (!timestamp) return '';
    try {
      const date = new Date(timestamp);
      return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
      });
    } catch (e) {
      return timestamp;
    }
  };

  // 角色徽章
  const renderRoleBadge = (member) => {
    if (member.status === 'creator') {
      return React.createElement('span', {
        className: 'inline-flex items-center px-2 py-1 bg-red-100 text-red-800 rounded-full text-xs'
      }, [
        React.createElement('svg', {
          key: 'icon',
          xmlns: 'http://www.w3.org/2000/svg',
          className: 'w-3 h-3 mr-1',
          fill: 'none',
          viewBox: '0 0 24 24',
          stroke: 'currentColor'
        }, 
          React.createElement('path', {
            strokeLinecap: 'round',
            strokeLinejoin: 'round',
            strokeWidth: 2,
            d: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z'
          })
        ),
        '群主'
      ]);
    } else if (member.status === 'administrator') {
      return React.createElement('span', {
        className: 'inline-flex items-center px-2 py-1 bg-blue-100 text-blue-800 rounded-full text-xs'
      }, [
        React.createElement('svg', {
          key: 'icon',
          xmlns: 'http://www.w3.org/2000/svg',
          className: 'w-3 h-3 mr-1',
          fill: 'none',
          viewBox: '0 0 24 24',
          stroke: 'currentColor'
        }, 
          React.createElement('path', {
            strokeLinecap: 'round',
            strokeLinejoin: 'round',
            strokeWidth: 2,
            d: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z'
          })
        ),
        '管理员'
      ]);
    }
    return null;
  };

  return React.createElement('div', {
    //className: 'bg-white rounded-lg shadow-md p-4 flex flex-col max-h-[calc(100vh-250px)] overflow-y-auto'
    className: 'bg-white rounded-lg shadow-md p-4 flex flex-col max-h-[600px] overflow-y-auto'
  }, [
    // 标题栏
    React.createElement('div', {
      key: 'header',
      className: 'flex items-center justify-between mb-4'
    }, [
      React.createElement('h2', {
        className: 'text-lg font-bold flex items-center gap-2'
      }, [
        React.createElement('svg', {
          className: 'w-5 h-5',
          fill: 'none',
          viewBox: '0 0 24 24',
          stroke: 'currentColor'
        }, 
          React.createElement('path', {
            strokeLinecap: 'round',
            strokeLinejoin: 'round',
            strokeWidth: 2,
            d: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z'
          })
        ),
        '群组成员列表'
      ]),
      selectedGroup && React.createElement('button', {
        onClick: () => fetchMembers(selectedGroup),
        className: 'p-2 text-gray-600 hover:text-gray-900 focus:outline-none',
        title: '刷新成员列表'
      }, 
        React.createElement('svg', {
          xmlns: 'http://www.w3.org/2000/svg',
          className: 'w-4 h-4',
          fill: 'none',
          viewBox: '0 0 24 24',
          stroke: 'currentColor'
        }, 
          React.createElement('path', {
            strokeLinecap: 'round',
            strokeLinejoin: 'round',
            strokeWidth: 2,
            d: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15'
          })
        )
      )
    ]),

    // 群组选择器
    React.createElement('div', {
      key: 'group-select',
      className: 'mb-4'
    }, 
      React.createElement('select', {
        className: 'w-full p-2 border rounded',
        value: selectedGroup || '',
        onChange: (e) => {
          const groupId = e.target.value;
          if (groupId) fetchMembers(groupId);
        }
      }, [
        React.createElement('option', { value: '' }, '选择群组'),
        ...groups.map((group) => 
          React.createElement('option', {
            key: group.id,
            value: group.id
          }, group.title)
        )
      ])
    ),

    // 成员统计信息
    selectedGroup && React.createElement('div', {
      key: 'stats',
      className: 'mb-4 p-3 bg-blue-50 rounded-lg'
    }, [
      React.createElement('div', { className: 'font-medium text-blue-800' }, 
        `${stats.chatTitle || '群组'} - 成员统计`
      ),
      React.createElement('div', { className: 'text-sm text-blue-600 mt-1' }, [
        `总成员数: ${stats.totalMembers}`,
        React.createElement('span', { className: 'mx-2' }, '•'),
        `可见成员: ${stats.visibleMembers}`
      ])
    ]),

    // 加载状态
    loading && React.createElement('div', {
      key: 'loading',
      className: 'text-center py-4'
    }, 
      React.createElement('div', {
        className: 'animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto'
      })
    ),

    // 错误信息
    error && React.createElement('div', {
      key: 'error',
      className: 'bg-red-100 text-red-800 p-3 rounded mb-4'
    }, error),

    // 成员列表
    !loading && !error && members.length > 0 && React.createElement('div', {
      key: 'members-list',
      className: 'space-y-2'
    }, 
      members.map((member) => 
        React.createElement('div', {
          key: member.user_id,
          className: 'flex flex-col p-3 bg-gray-50 rounded hover:bg-gray-100'
        }, [
          // 主要信息行
          React.createElement('div', {
            className: 'flex items-center justify-between'
          }, [
            React.createElement('div', {
              className: 'flex items-center gap-3'
            }, [
              // 头像占位符
              React.createElement('div', {
                className: 'w-10 h-10 bg-gray-200 rounded-full flex items-center justify-center'
              }, 
                React.createElement('svg', {
                  xmlns: 'http://www.w3.org/2000/svg',
                  className: 'w-6 h-6 text-gray-600',
                  fill: 'none',
                  viewBox: '0 0 24 24',
                  stroke: 'currentColor'
                }, 
                  React.createElement('path', {
                    strokeLinecap: 'round',
                    strokeLinejoin: 'round',
                    strokeWidth: 2,
                    d: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z'
                  })
                )
              ),
              React.createElement('div', { className: 'flex-1' }, [
                // 用户名和身份信息
                React.createElement('div', {
                  key: 'name',
                  className: 'font-medium flex items-center gap-2'
                }, [
                  member.full_name,
                  renderRoleBadge(member)
                ]),
                // 用户名和ID
                React.createElement('div', {
                  key: 'info',
                  className: 'text-sm text-gray-500'
                }, [
                  member.username && `@${member.username}`,
                  React.createElement('span', { className: 'mx-1' }, '•'),
                  `ID: ${member.user_id}`
                ])
              ])
            ]),
            // 操作按钮
            React.createElement('button', {
              className: 'text-blue-600 hover:text-blue-800',
              onClick: () => {
                // 发送自定义事件以填充禁言表单
                const event = new CustomEvent('fillMuteForm', {
                  detail: {
                    chatId: selectedGroup,
                    userId: member.user_id
                  }
                });
                window.dispatchEvent(event);
              }
            }, '禁言')
          ]),
          // 最后活跃时间
          member.last_active && React.createElement('div', {
            className: 'mt-2 text-xs text-gray-500'
          }, `最后活跃: ${formatLastActive(member.last_active)}`)
        ])
      )
    ),

    // 空状态
    !loading && !error && members.length === 0 && selectedGroup && React.createElement('div', {
      key: 'empty',
      className: 'text-center py-4 text-gray-500'
    }, '暂无可见成员信息')
  ]);
}

// 将组件暴露到全局作用域
window.GroupMembersPanel = GroupMembersPanel;