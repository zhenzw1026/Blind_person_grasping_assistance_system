# Project 前端模块接入蓝图（不改后端核心逻辑）

## 1. 目标与边界

### 1.1 目标
- 在 project 内新增完整前端模块（参考 frontend 现有 UI/交互）。
- 新增 Web API 适配层，供前端实时调用。
- 保持后端核心算法逻辑不变：检测、引导策略、语音/日志等现有能力继续复用。

### 1.2 明确不改动
- 不修改 grasp_assist/pipeline.py 中核心引导逻辑。
- 不修改 grasp_assist/detectors/*.py 的检测策略语义。
- 不修改 grasp_assist/guidance/policy.py 的指导策略语义。
- 不改变 configs/default.yaml 的配置含义，仅允许通过 API 做运行时参数覆盖。

## 2. 最终产品使用逻辑（用户视角）

1. 用户进入首页，点击“开始使用”或先进入设置。
2. 在设置页配置：语速、离线模式、摄像头、方向反转。
3. 进入辅助页后点击“开始”，系统打开摄像头并进入“等待目标语音”状态。
4. 用户说“帮我找手机”等目标指令，系统创建 session 并绑定目标物体。
5. 前端按固定节奏上传视频帧，后端返回当前阶段、引导语、检测结果。
6. 前端将引导语语音播报，并叠加目标框/手部框/调试信息。
7. 用户可随时语音说“停止/重置/换目标”，系统按意图切换。
8. 到达 done 后提示任务完成，可继续下一个目标或结束。
9. 会话结束后在 outputs/session_xxx 中产生日志与 summary 指标。

## 3. 系统分层与模块划分

### 3.1 前端层（新增到 project）
- 职责：页面交互、摄像头采集、语音输入/播报、实时可视化、会话控制。
- 建议结构：
  - web/app/page.tsx：首页
  - web/app/assist/page.tsx：实时辅助页
  - web/app/settings/page.tsx：设置页
  - web/components/LiveAssistant.tsx：核心交互组件
  - web/lib/api.ts：后端 API 调用
  - web/lib/settings.ts：本地设置存储
  - web/types/api.ts：前后端类型契约

说明：UI 与交互可迁移自 frontend 中对应文件，视觉风格保持一致。

### 3.2 API 适配层（新增到 project）
- 职责：把 HTTP 请求转换为对既有引擎能力的调用，不重写算法。
- 建议结构：
  - backend_api/main.py：应用入口
  - backend_api/models.py：请求/响应模型
  - backend_api/session_manager.py：session 生命周期管理
  - backend_api/bridge.py：调用 grasp_assist 能力的桥接

说明：
- 适配层负责 session、并发安全、参数校验、错误处理。
- 适配层不承载检测与策略业务规则。

### 3.3 核心引擎层（现有 project）
- grasp_assist/pipeline.py：视觉+语音主流程核心能力。
- grasp_assist/detectors/*：手部与物体检测。
- grasp_assist/guidance/policy.py：方向与抓取指令生成。
- grasp_assist/eval/*：指标统计与会话日志。
- configs/default.yaml：运行参数。

## 4. 运行时状态机定义

统一状态（与前端 types/api.ts 保持一致）：
- searching
- target_locked
- approaching
- near_field
- grasp_guide
- done

### 4.1 状态语义
- searching：未稳定定位目标，给出搜索方向提示。
- target_locked：目标已稳定锁定，准备引导手部。
- approaching：手部朝目标靠近过程。
- near_field：手与目标进入近场，提醒慢动作。
- grasp_guide：进入抓取动作指导。
- done：判定抓取完成。

### 4.2 关键转换条件（逻辑层）
- searching -> target_locked：目标检测稳定满足阈值。
- target_locked -> approaching：检测到手部并开始相对位移引导。
- approaching -> near_field：目标面积/手目标距离进入近场区间。
- near_field -> grasp_guide：方向基本对准，可执行抓取动作。
- grasp_guide -> done：命中抓取判定（重叠/中心距/触达规则）。
- 任意状态 -> searching：reset 或目标丢失超时后回退。
- 任意状态 -> done：收到 complete 意图或停止流程。

## 5. API 契约（与现有 frontend 保持兼容）

### 5.1 POST /api/session/start
请求：
- target_label: string

响应：
- session_id: string
- target_label: string
- state: GuideState
- current_instruction: string

用途：创建新任务会话并初始化状态。

### 5.2 POST /api/session/{session_id}/settings
请求：
- speech_rate: slow | medium | fast
- offline_mode: boolean

响应：
- 204 或空对象

用途：下发会话级设置，不改变全局配置文件语义。

### 5.3 POST /api/vision/frame
请求：
- session_id: string
- frame_width: number
- frame_height: number
- mirror_x: boolean
- image_b64: string
- server_detect: boolean
- detect_conf: number
- detections: []

响应：
- state: GuideState
- instruction: string
- confidence: number
- target_found: boolean
- distance_hint: far | mid | near | null
- target_box: BoundingBox | null
- hand_box: BoundingBox | null
- detection_items: DetectionItem[]
- debug: object | null

用途：实时帧推理主接口。

### 5.4 POST /api/voice/command
请求：
- session_id: string
- transcript: string
- offline_mode: boolean

响应：
- intent: string
- target_label?: string
- should_interrupt: boolean
- feedback: string

用途：处理用户语音意图（换目标、停止、完成等）。

### 5.5 POST /api/session/{session_id}/reset
请求：无

响应：
- 204 或空对象

用途：重置当前任务进度，保留会话上下文。

## 6. 前后端时序（端到端）

1. 前端 Start -> /api/session/start。
2. 前端 /settings 下发 -> /api/session/{id}/settings。
3. 前端每 180-250ms 上传帧 -> /api/vision/frame。
4. 后端返回 instruction/state/detections。
5. 前端播报 instruction，并更新叠加框。
6. 用户语音 -> /api/voice/command。
7. 若返回 should_interrupt=true：前端停止循环并结束会话。
8. 若返回新 target_label：前端重新 start 新目标流程。
9. 用户 Reset -> /api/session/{id}/reset。
10. done 后停止帧循环，展示完成态。

## 7. 落地实施顺序（建议）

1. 在 project 新增 API 适配层骨架与健康检查接口。
2. 建立 session manager（内存态）与基础模型定义。
3. 先打通 /api/session/start 与 /api/session/{id}/settings。
4. 打通 /api/vision/frame（最小返回），再补齐 detection_items/debug。
5. 打通 /api/voice/command 与 /api/session/{id}/reset。
6. 将 frontend UI 迁入 project/web 并替换 API base。
7. 端到端联调：摄像头、语音、状态机、日志输出。
8. 压测与健壮性：高频帧、网络抖动、重复指令去抖。

## 8. 验收标准

- 用户可在浏览器完成“说目标 -> 实时引导 -> 抓取完成”全流程。
- 所有前端页面可访问且移动端/桌面端可正常显示。
- 不改动核心算法逻辑文件时，流程可稳定运行。
- outputs 目录按会话生成 frames.csv 与 summary.json。
- 语音中断、重置、换目标都能正确落状态。

## 9. 风险与控制

- 风险：核心 pipeline 目前偏 CLI 循环式，不是天然请求响应式。
- 控制：通过 bridge 层做“帧级调用包装”，避免侵入核心算法。

- 风险：浏览器端语音识别可用性受环境影响。
- 控制：保留按钮触发的 PTT 模式与连续监听双模式。

- 风险：摄像头镜像导致左右指令反转。
- 控制：保留 directionFlip 并在 frame 接口明确 mirror_x。

---

该文档用于后续在 project 中实施“前端接入 + API 适配”的唯一蓝图，开发阶段以此为准并保持与 frontend 现有交互兼容。
