# 交互式视觉辅助抓取系统

本项目用于课程工程实践：通过实时视觉检测与语音反馈，辅助用户找到并抓取目标物体。

## 项目结构

- grasp_assist/: 核心算法与流程
- grasp_assist/detectors/: 手部与目标检测
- grasp_assist/guidance/: 指令生成策略
- grasp_assist/audio/: 语音播报
- grasp_assist/eval/: 运行指标与会话日志
- configs/default.yaml: 运行配置
- run_demo.py: 本地演示入口（OpenCV 窗口）
- run_api.py: Web API 入口（给前端调用）

## 环境要求

- 操作系统：Windows
- Python：建议 3.12（当前依赖栈在 3.13 上兼容性较差）
- 建议在 project 目录内创建独立虚拟环境，避免与 Anaconda 全局环境混用

## 快速开始（完整可执行步骤）

以下命令请在项目目录 project 中执行。

1. 进入目录

```powershell
cd project
```

2. 创建虚拟环境（Python 3.12）

```powershell
python -m venv .venv
```

3. 安装稳定打包工具链

```powershell
.\.venv\Scripts\python.exe -m pip install pip==25.1.1 setuptools==70.3.0 wheel==0.45.1
```

4. 安装项目依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt --no-build-isolation
```

5. 验证解释器是否正确

```powershell
.\.venv\Scripts\python.exe -V
```

如果输出不是 Python 3.12.x，请不要继续，先检查创建环境时使用的 Python 路径。

## 启动方式

### 方式 A：本地演示（OpenCV 窗口）

在 project 目录执行：

```powershell
.\.venv\Scripts\python.exe run_demo.py --config configs/default.yaml
```

退出方式：按 q 或 Esc。

### 方式 B：前后端联调（推荐）

请使用两个终端分别启动后端和前端。

1. 终端 A：启动后端 API（project 目录）

```powershell
cd project
python run_api.py
```

2. 终端 B：启动前端（frontend 目录）

```powershell
cd frontend
npm install
npm run dev
```

3. 打开前端页面

```text
http://localhost:3000
```

4. 健康检查（可选，后端需返回 ok）

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health | ConvertTo-Json -Compress
```

预期返回：

```json
{"status":"ok"}
```

## 离线评估

```powershell
.\.venv\Scripts\python.exe evaluate_video.py --video path\to\demo.mp4 --config configs/default.yaml
```

## 常见问题与处理

### 1) pip install 成功，但 run_api.py 仍报缺包

原因：依赖装到了错误的 Python 环境（例如 Anaconda），不是 project/.venv。

处理：

```powershell
where python
.\.venv\Scripts\python.exe -m pip show fastapi uvicorn
```

如果第二条显示找不到包，重新执行安装命令并确保使用 .venv\Scripts\python.exe。

### 2) 提示找不到 configs/default.yaml

原因：从错误目录启动导致相对路径失效。

处理：先 cd 到 project 再启动，或始终使用上面的标准启动命令。

### 3) Windows 安全中心拦截未知 output.exe

这通常来自依赖安装过程中的临时构建文件，与项目源码无关。建议：

- 使用 Python 3.12 + 本文档固定安装步骤
- 在 project/.venv 内安装，不要混用系统 Python
- 如遇拦截，先关闭安装进程，再按本文档重新安装

### 4) OpenCV 窗口中文显示乱码

确认 configs/default.yaml 中字体配置有效：

```yaml
runtime:
  ui_enable_unicode: true
  ui_font_path: C:/Windows/Fonts/msyh.ttc
```

### 5) 报错 ENOENT：spawn ...\\.venv\\Scripts\\python.exe

典型报错：

```text
Error spawning python: spawn ...\\project_frontend\\.venv\\Scripts\\python.exe ENOENT
```

原因：VS Code 正在使用工作区根目录下不存在的 .venv，而当前项目环境在 project/.venv。

处理步骤：

1. 在 VS Code 中按 Ctrl+Shift+P，执行 Python: Select Interpreter。
2. 选择 E:\\Polyu\\SEM2\\5523CV\\project_frontend\\project\\.venv\\Scripts\\python.exe。
3. 在 project 目录重新执行安装命令：

```powershell
cd E:\Polyu\SEM2\5523CV\project_frontend\project
.\.venv\Scripts\python.exe -m pip install pip==25.1.1 setuptools==70.3.0 wheel==0.45.1
```

## 当前能力

- 手部跟踪：MediaPipe Hands
- 目标检测：YOLO / YOLO-World（可配置）
- 引导输出：方向与距离提示 + 抓取完成判定
- 语音：本地 TTS + Whisper 识别（可选 Google 兜底）
- 日志：输出到 outputs/session_*/frames.csv 与 summary.json

## 常用中文语音指令

- 帮我找手机
- 我要找杯子
- 找钥匙
- 帮我找鼠标
- 结束
