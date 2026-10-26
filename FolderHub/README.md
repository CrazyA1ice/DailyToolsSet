# FolderHub：本地文件夹导航中心

Windows 本地网页版文件夹快捷导航工具：用“模块 / 子模块”组织电脑上的科研、工作和开发文件夹，点击已关联的文件夹卡片即可通过**Windows 文件资源管理器**打开。**不会移动、重命名或删除真实文件。**

![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab) ![Dependency](https://img.shields.io/badge/第三方依赖-零-success) ![Platform](https://img.shields.io/badge/Windows-10%2F11-blue)

## 快速启动

1. Windows 10/11 安装 Python 3.10 或更新版本（安装时勾选“Add Python to PATH”）。
2. 双击 `start_windows.bat`，或在命令行运行 `python app.py`。
3. 浏览器会自动打开 `http://127.0.0.1:8765/`。**不要关闭启动窗口**，窗口关闭时服务停止。
4. 点击“新建根模块”建立一级分类；通过普通模块继续嵌套，最末级使用叶子模块。
5. 创建叶子模块时点击“浏览...”选择已有本地文件夹（也可以粘贴绝对路径），保存后点击卡片即可在系统文件资源管理器中打开文件夹。

服务仅监听本机 `127.0.0.1`，不向局域网或互联网暴露端口。不调用云服务，也不会上传你的文件。

## 已实现功能

- **分类型无限层级目录树**：根模块只允许最顶层；普通模块可无限嵌套；叶子模块必须关联一个文件夹且不可再拥有子模块。左侧目录支持逐层展开/折叠并记住状态。
- **增删查改**：新增、修改名称、修改路径、调整父模块、删除当前模块及其子模块导航记录（**永不删除真实文件夹**）。
- **打开文件夹**：绑定了路径的卡片单击即可调用 `os.startfile()`，通过 Windows 系统 Shell 打开资源管理器；不存在的路径会提示错误。
- **文件夹选择**：通过 Python 标准库 tkinter 弹出 Windows 原生文件夹选择对话框。
- **收藏和全局搜索**：按模块名称、关联文件夹路径、完整所属分类路径搜索全部层级；显示结果归属层级；支持 `Ctrl+K` 聚焦搜索、收藏及网格/列表切换。
- **备份恢复**：通过 JSON 文件导出与恢复全部导航结构；恢复操作将**替换当前配置**，不会更改磁盘文件。
- **持久化**：SQLite 自动保存。数据路径为 `%LOCALAPPDATA%\DailyToolsSet\FolderHub\folderhub.db`，卸载/更新源代码不会丢失记录。

> 注意：浏览器安全机制不允许普通静态 HTML 直接打开 Windows 文件资源管理器，因此需要同时运行本地 Python 服务。不能将纯静态页面托管到 GitHub Pages 后实现本地文件夹打开功能。

## 常用启动命令

```powershell
# 在 FolderHub 目录内执行
python app.py                     # 默认 8765 端口，自动打开浏览器
python app.py --port 8770         # 指定其他端口
python app.py --no-browser        # 不自动打开浏览器
python app.py --data-dir "D:\FolderHubData"   # 自定义数据库目录
python -m unittest discover -s tests -v      # 运行全部测试
```

自定义数据目录也支持环境变量 `FOLDERHUB_DATA_DIR`。首次使用 Windows 的文件夹浏览功能需要 Python 自带 tkinter（标准 Windows Python 安装一般包含）。

## 架构和安全边界

```text
FolderHub/
├── app.py                 # Python 标准库 HTTP + SQLite 后端
├── start_windows.bat      # Windows 一键启动
├── static/
│   ├── index.html         # 网页主界面
│   ├── styles.css         # 样式
│   ├── app.js             # 无依赖交互逻辑
│   └── favicon.svg
├── tests/
│   └── test_app.py        # 数据库和 HTTP 安全/CRUD 测试
├── .gitignore
└── README.md
```

HTTP 服务固定绑定 `127.0.0.1`；写入类请求需要动态令牌和 JSON Content-Type，并检验请求 Origin、Host，避免普通恶意网页直接发送文件夹打开请求。目录路径保存时要求绝对路径；实际打开时检查目录存在。服务不会执行用户输入的 shell 字符串。**此工具用于可信任的本机个人环境，不是可供外网部署的多用户文件管理服务器。**

## 首次上传 GitHub

如果远程仓库是空的，在**DailyToolsSet 仓库根目录**运行：

```bash
git init
git remote add origin https://github.com/CrazyA1ice/DailyToolsSet.git
git add .
git commit -m "feat: add FolderHub local folder dashboard"
git branch -M main
git push -u origin main
```

如果当前目录已经是 Git 仓库，**省略** `git init` 和 `git remote add origin`。如果报 `remote origin already exists`，可用 `git remote -v` 检查远端。`src refspec main does not match any` 常见于尚未创建首次 commit，或本地仍位于 `master` 分支；先 `git add .` 和 `git commit`，再 `git branch -M main` 后 push。

**不要把运行时数据库、私人路径备份文件或其他隐私文件上传到公开仓库。** Git 忽略了常见的 `.db` 文件，但自定义备份命名的 JSON 仍可能被 Git 跟踪，提交前请务必检查 `git status`。

## V1.1：开机启动、浏览器首页与换肤

### 开启 Windows 登录自启动

1. 正常运行 `start_windows.bat`，打开 FolderHub 页面。
2. 点击页面右上角 **「设置」**（也可点「换肤」），在“开机自启动”中打开开关。
3. 下次**登录 Windows 用户账户**后，系统将通过 `pythonw.exe` 静默启动本地服务，不会自动再打开一个浏览器窗口。
4. 关闭开关可删除相同启动项。关闭开关不会立即结束已经在运行的本地服务。

实现采用当前用户专属的注册表项 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`，仅添加或移除名为 `DailyToolsSet.FolderHub` 的值；**默认不开启，不修改其他启动项，也无需管理员权限**。这是登录后启动，而不是在操作系统未登录时作为 Windows 服务运行。需要完整 Windows Python 安装中包含 `pythonw.exe`，且安装位置及本工具 `FolderHub` 文件夹路径保持不变。移动文件夹或切换 Python 环境后，需重新打开开关以更新启动路径。建议将本工具放在稳定的本地目录，不要放在会被临时清理的路径。

如需使用命令行管理：

```powershell
# 在 FolderHub 目录内
python app.py --startup status
python app.py --startup enable
python app.py --startup disable
```

Windows 可在 **设置 → 应用 → 启动** 中查看启用情况。在某些系统配置下，安全软件或 Windows 的应用启动开关可能阻止已登记的应用真正运行。若正在运行 FolderHub，请不要重复启动服务（默认占用端口 8765）。

### 设为浏览器“启动时打开的页面”

请先启动 FolderHub、开启开机自启动，再将下面的网址设置为浏览器启动页：

```text
http://127.0.0.1:8765/
```

- **Google Chrome**：设置 → **启动时** → **打开特定网页或一组网页** → 添加新网页，填入上述地址。
- **Microsoft Edge**：设置 → **开始、主页和新建标签页** → **当 Edge 启动时** → 打开以下页面 → 添加新页面。
- 若仅想把它设为主页按钮跳转地址，可在浏览器“外观/主页按钮”中设置相同 URL。

**区别：**“启动时打开”不等于“每次新建标签页”。若要求每个新标签页都显示 FolderHub，通常需要浏览器扩展。本项目不为此添加扩展或修改浏览器策略。Windows 启动应用程序和浏览器启动进程顺序不受本工具控制，因此刚登录时可能短暂显示无法连接，此时刷新即可。

### 换肤

页面右上角的“换肤”可选择 **云白 / 午夜 / 雾森 / 暖沙 / 跟随系统**。主题标记保存在**当前浏览器的 localStorage**，不更改文件夹数据库，也不需要外网下载壁纸或 CSS。使用其他浏览器时需要单独设置。若清理浏览器站点数据，外观会恢复默认云白；文件导航数据仍存在 SQLite 中。

界面布局参考 [Homer Minimal](https://github.com/tchgrbr/homer-minimal) 的明晰卡片分组，以及 [Flame](https://github.com/pawelmalak/flame) 的浏览器起始页与主题配置理念；本项目未复制其源码或资产。整体仍由原生 HTML、CSS 和 JavaScript 构建，保持**零第三方依赖**。

### 排障提示

- 页面提示「无法连接」：确认 Python 服务已经运行，检查防火墙 / 是否误关闭启动窗口。仅绑定 `127.0.0.1`，无需放行局域网端口。
- 开机自启动不可用：确保安装的是 Windows Python 且存在 `pythonw.exe`，使用网页开关或 `python app.py --startup status` 查看状态。
- 已启动后重复运行提示 8765 端口被占用：说明可能有另一个 FolderHub 进程正在运行，直接打开网页即可。
- **本机安全**：自启动在后台运行的 Python 服务可触发打开系统资源管理器，因此仅供可信的个人 Windows 账户使用。不要部署到公网，也不要把真实路径的 JSON 备份上传公开仓库。


## V1.2：根模块、叶子模块、分层导航与全局搜索

| 类型 | 放置位置 | 能否继续建下级模块 | 绑定文件夹 |
| --- | --- | --- | --- |
| 根模块 | 只能在目录最顶层 | 可以 | 新创建时不允许；旧版已有绑定将被保留 |
| 普通模块 | 必须位于其他分类模块下 | 可以 | 新创建时不允许；旧版已有绑定将被保留 |
| 叶子模块 | 必须位于根模块或普通模块下 | **不可以** | **必须且仅能绑定一个文件夹** |

- 新建、编辑模块时可明确选择类型；修改为叶子模块前必须先移动或移除其全部下级模块。
- 左侧目录是可折叠树，点击小箭头展开/折叠，点击文字进入分类；点击叶子模块文字则调用 Windows 文件资源管理器打开关联目录。
- 页面全局搜索不受当前目录限制，支持多关键词搜索，并显示匹配结果完整上级分类；搜索范围为**导航模块名称和已登记路径，不会扫描磁盘内文件内容**。
- 第一次启动新版会在已有 SQLite 表上新增 `node_type` 字段，并推断旧记录类型：顶层为根模块、有子模块的为普通模块，其余已绑定文件夹的非顶层末级记录为叶子模块。旧版分类模块关联的历史文件夹路径不会被删除。
- 备份格式升级至 `version: 2`，仍可导入版本 1 的备份。建议升级前先使用页面的“备份”功能导出一份文件。
- 修改仅涉及 `FolderHub/` 目录，数据仍存储在 `%LOCALAPPDATA%\DailyToolsSet\FolderHub\folderhub.db`。
