@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 app.py
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo 启动失败：未找到 Python，请安装 Python 3.10 或更高版本。
    pause
    exit /b 1
  )
  python app.py
)
set "folderhub_exit=%errorlevel%"
if not "%folderhub_exit%"=="0" (
  echo.
  echo FolderHub 启动或运行失败（退出码 %folderhub_exit%），请查看上方的具体 Python 错误信息。
  echo 如果提示 WinError 32，请先退出仍在运行的 FolderHub 后台或托盘进程再重试。
  pause
)
exit /b %folderhub_exit%
