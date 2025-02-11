1、新建必要的文件夹
mkdir -p /home/tel_group_ass/static/js

2、将必要的文件内容复制下来，并放入对应的文件夹，文件树如下：

/home/tel_group_ass
├── static
│   ├── index.html
│   ├── js
│   │   ├── GroupAdminPanel.js
│   │   └── messages.js
│   └── login.html
└── telegram-bot.py


文件都保存好后，记得改属性
chmod +x /home/tel_group_ass/telegram-bot.py /home/tel_group_ass/static/login.html /home/tel_group_ass/static/index.html
chmod +x /home/tel_group_ass/static/js/GroupAdminPanel.js /home/tel_group_ass/static/js/messages.js

或者你也可以直接从github上克隆下来（未完成，待补）

这些文件你需要修改的地方有：
telegram-bot.py中
66行，你的机器人token api ：TOKEN = "your-token"
67行，生成机器人token api的telegram 账号id ：ADMIN_ID = 66666666
68行，你的网址：WEBHOOK_URL = "https://your.website.com/webhook"
131行，登录你的网址的密码：ACCESS_TOKEN = "passwall"
其他主体文件就不需要修改，直接用即可

3、nginx的配置
因为用了webhook，所以要用反代，nginx的配置文件你可以放到你的nginx的conf文件夹内，nginx内需要修改的地方为：
4行，你的网址，和telegram-bot.py中的网址保持一致
6、7行，证书地址

4、配置进程保护telegram_group_assistant.service
touch /etc/systemd/system/telegram_group_assistant.service
nano /etc/systemd/system/telegram_group_assistant.service

填入以下内容：
[Unit]
Description=Telegram Group assistant
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/tel_group_ass
ExecStart=/root/venv/bin/python /home/tel_group_ass/telegram-bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target

ctrl +x 保存后退出

5、配置python虚拟环境（如果你是高手，也可以不用python虚拟环境）
步骤 1: 安装虚拟环境支持工具
首先，确保你的系统安装了 python3-venv 包，这允许你创建和管理虚拟环境。

sudo apt update
sudo apt install python3-venv
步骤 2: 创建一个虚拟环境
选择一个目录来创建虚拟环境。例如，你可以在你的用户目录下创建一个名为 venv 的环境：
python3 -m venv ~/venv

这将在你的主目录中创建一个名为 venv 的文件夹，里面包含了独立的 Python 执行器和 pip 工具。

步骤 3: 激活虚拟环境
在安装任何包之前，你需要激活虚拟环境：
source ~/venv/bin/activate
当虚拟环境被激活后，你会看到命令提示符前面有环境的名称，这表明接下来的所有 Python 和 pip 命令都将在这个隔离的环境中执行。

要退出虚拟环境：
deactivate
6、进入虚拟环境，安装必要的工具
source ~/venv/bin/activate
pip install Flask request  jsonify  session  redirect  url_for  send_file timedelta httpx HTTPXRequest RotatingFileHandler check_password_hash

（如果运行的时候提示缺少工具，那么就pip install 这个工具名字）

7、确保上面步骤都操作和填写好你的信息后，就可以启动进程了
输入：
sudo systemctl daemon-reload

sudo systemctl enable telegram_group_assistant.service

sudo systemctl start telegram_group_assistant.service

sudo systemctl status telegram_group_assistant.service

8、你需要将你的机器人加入到群内，并升级为admin管理员，就可以愉快的管理群了。
输入你的网址，会提示你输入密码后，就能见到操作界面

9、目前还缺少的功能有：
缺少进群验证，这个后续再让我的职员claude.ai以及chatgpt帮我写出来，各位MJJ有什么建议也可以说一下，我的职员不一定有这个能力写出来

