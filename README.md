# 🎙️ Full Pipeline — AI 情感叙述语音合成管线

> 将 Markdown 叙事文本转化为**富有情感起伏、节奏变化**的有声叙述音频 (WAV)。

---

## 📦 项目结构

```
full_pipline/
├── narrator_2.py        # ★ 主管线：端到端 TTS 合成（LLM → 状态融合 → 音频输出）
├── narrator_json_1.py   # 辅助管线：批量 LLM 情感曲线提取 → JSON（用于调试/预分析）
├── tts_engine.py         # TTS 引擎（模拟合成 + librosa 语速后处理）
├── utils.py              # 工具集：文本加载、分句、曲线插值、WAV 保存
├── requirements.txt      # Python 依赖
├── A_T3.md               # 示例输入 — 现代文学叙事（Detroit 悬疑）
├── Aviator_T1.md         # 示例输入 — 历史年代叙事（Rust Belt 家族史）
└── README.md             # ← 你在这里
```

---

## 🧠 核心架构：两级管线

```
┌──────────────────────────────────────────────────────────────┐
│                     narrator_2.py（主管线）                    │
│                                                              │
│  Markdown ──→ 段落切分 ──→ LLM 情感曲线 ──→ 状态融合          │
│                                      ↓                       │
│                          智能分块 → 曲线插值 → 载荷校验        │
│                                      ↓                       │
│                          逐 chunk TTS 合成 → WAV 拼接输出     │
└──────────────────────────────────────────────────────────────┘


┌──────────────────────────────────────────────────────────────┐
│                  narrator_json_1.py（预分析管线）               │
│                                                              │
│  Markdown ──→ 段落切分 ──→ 并行 LLM 调用 (max_workers=15)     │
│                                      ↓                       │
│                          输出 JSON（情感曲线原始数据，不进 TTS） │
└──────────────────────────────────────────────────────────────┘
```

---

## 🔧 模块详解

### 1. `narrator_2.py` — 主合成管线

| 阶段 | 函数/类 | 作用 |
|------|---------|------|
| **LLM 情感解析** | `generate_curves(text)` | 调用 DeepSeek V4 Flash 分析文本，生成情绪曲线、韵律曲线、节拍标记 |
| **叙事状态机** | `NarrativeState` | 维护全局 `tension`（紧张度）和 `pace`（节奏），高潮节拍增压减速，释放节拍减压增速 |
| **曲线融合** | `fuse_curve()` | 将 LLM 生成曲线与叙事状态融合：`emo_alpha × tension`，`speech_rate × pace` |
| **载荷构建** | `build_tts_payload()` | 构造 IndexTTS 标准请求体，`emo_vector` 长度=8，值域 [0,1] |
| **载荷校验** | `validate_payload()` | 严格断言校验，失败时大声报错而非静默吞掉 |
| **主调度** | `run()` | 编排上述所有步骤，输出完整 WAV |

### 2. `narrator_json_1.py` — 预分析管线

- 使用 **ThreadPoolExecutor (max_workers=15)** 并行调用 LLM
- 保留原始顺序输出 JSON，便于人工审查情感曲线质量
- 单段落异常不影响全局（try/except 兜底）

### 3. `tts_engine.py` — TTS 引擎

```python
def tts_generate(text, emo_vector, emo_alpha, speed, audio_prompt)
```

- **当前为模拟实现**：生成随机噪声 + librosa 时间拉伸实现变速
- 架构预留了真实的 IndexTTS API 接入点（payload 结构已对齐）
- `speed` 参数通过后处理实现，非模型原生参数

### 4. `utils.py` — 工具函数集

| 函数 | 功能 |
|------|------|
| `load_markdown(path)` | 读取 Markdown，去除标题/粗体/链接，按空行分段 |
| `smart_split(text)` | 按句号分句并合并至 ~120 字符/chunk |
| `interp_curve(curve, t)` | 在时间轴上对情绪/韵律曲线做线性插值 |
| `save_wav(chunks, path)` | 拼接所有 audio chunk 并保存为 24kHz WAV |

---

## 🚀 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 使用主管线（端到端合成）

```bash
python narrator_2.py A_T3.md -o output.wav
```

参数说明：
- `input` — 输入 Markdown 文件路径（必需）
- `-o / --output` — 输出 WAV 路径（默认 `narrated.wav`）

### 使用预分析管线（仅提取情感曲线）

```bash
python narrator_json_1.py
# 当前硬编码为 Aviator_T1.md → Aviator_T1.json
# 也可自行修改文件末尾的 input_path / output_path
```

---

## 🧩 关键技术设计

### 1. 叙事状态机

```
        高潮节拍 (climax beat)
    ┌─────────────────────────┐
    │  tension × 1.2 (↑)      │
    │  pace    × 0.9 (↓)      │
    └─────────────────────────┘

        释放节拍 (release beat)
    ┌─────────────────────────┐
    │  tension × 0.8 (↓)      │
    │  pace    × 1.05 (↑)     │
    └─────────────────────────┘
```

- 范围限制：`tension ∈ [0.1, 2.0]`, `pace ∈ [0.5, 1.5]`
- 效果：剧情高潮时声音更有力、语速放缓；释放时声音柔和、语速恢复正常

### 2. 防御性编程

| 风险场景 | 防护措施 |
|---------|---------|
| LLM 返回 ````json...```` 包裹 | 正则剥离 markdown 代码块 |
| LLM 返回 `"beats": null` | `.get("beats") or []` |
| LLM 缺失 `emo_curve` / `prosody_curve` | 使用默认曲线兜底 |
| `emo_vector` 非 8 维或越界 | `validate_payload()` 断言校验 |
| 单段落 LLM 调用失败（json_1） | try/except 返回错误标记 |

### 3. IndexTTS Payload 规范

```python
{
    "text": "待合成的文本块",
    "emo_vector": [0, 0, 0.3, 0.3, 0, 0.5, 0, 0.4],  # 8 维情绪向量
    "emo_alpha": 0.8,             # [0, 1] 情绪强度
    "use_emo_text": False,        # 禁用文本标记叠加
}
```

---

## 📂 示例输入说明

### `A_T3.md` — 现代文学叙事
- 风格：冷峻、悬疑、心理描写
- 场景：Detroit 雨夜，作家面对父亲谋杀案的心理挣扎
- 情感特征：压抑 → 爆发 → 释然

### `Aviator_T1.md` — 年代家族叙事
- 风格：厚重、历史感、群像描写
- 场景：1979 年 Rust Belt，印刷工人与家族恩怨
- 情感特征：缓慢铺陈 → 冲突积累 → 高潮释放

---

## 🔮 未来扩展方向

- [ ] **真实 IndexTTS 引擎接入**：替换 `tts_engine.py` 中的模拟噪声为真实模型调用
- [ ] **语音克隆支持**：通过 `spk_audio_prompt` 参数接入说话人音色
- [ ] **更丰富的情绪维度**：当前 8 维情绪向量可扩展为更细粒度的情绪空间
- [ ] **流式输出**：支持长文本的流式音频生成，避免大文件 OOM
- [ ] **多语言支持**：扩展 LLM prompt 和分句逻辑以支持中文等语言

---

## 📜 依赖

| 包 | 用途 |
|----|------|
| `openai` | LLM API 调用（DeepSeek V4 Flash） |
| `numpy` | 音频数组操作 |
| `soundfile` | WAV 文件读写 |
| `librosa` | 音频时间拉伸（语速后处理） |
| `pydub` | 备用音频处理（当前未使用） |

---

## 📝 License

MIT
