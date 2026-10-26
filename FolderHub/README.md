# FolderHub：本地文件夹导航中心

Windows 本地网页版文件夹快捷导航工具：用“模块 / 子模块”组织电脑上的科研、工作和开发文件夹，点击已关联的文件夹卡片即可通过**Windows 文件资源管理器**打开。**不会移动、重命名或删除真实文件。**

![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab) ![Dependency](https://img.shields.io/badge/第三方依赖-零-success) ![Platform](https://img.shields.io/badge/Windows-10%2F11-blue)

## 快速启动

1. Windows 10/11 安装 Python 3.10 或更新版本（安装时勾选“Add Python to PATH”）。
2. 双击 `start_windows.bat`，或在命令行运行 `python app.py`。
3. 浏览器会自动打开 `http://127.0.0.1:8765/`。**不要关闭启动窗口**，窗口关闭时服务停止。
4. 点击“新建模块”建立一级分类；进入一级模块后点击“新建子模块”，可继续任意层级嵌套。
5. 在编辑窗口里点击“浏览...”选择已有本地文件夹（也可以粘贴绝对路径），保存后点击关联卡片，即可在系统文件资源管理器中打开文件夹。

服务仅监听本机 `127.0.0.1`，不向局域网或互联网暴露端口。不调用云服务，也不会上传你的文件。

## 已实现功能

- **不限层级模块树**：建立论文、代码项目、课程资料等主类，支持任意多层子模块；模块可以作为纯分类节点，亦可同时绑定本地文件夹。
- **增删查改**：新增、修改名称、修改路径、调整父模块、删除当前模块及其子模块导航记录（**永不删除真实文件夹**）。
- **打开文件夹**：绑定了路径的卡片单击即可调用 `os.startfile()`，通过 Windows 系统 Shell 打开资源管理器；不存在的路径会提示错误。
- **文件夹选择**：通过 Python 标准库 tkinter 弹出 Windows 原生文件夹选择对话框。
- **收藏和全局搜索**：可按模块名称及对应路径搜索全部层级、设置/取消收藏、切换网格/列表。
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
