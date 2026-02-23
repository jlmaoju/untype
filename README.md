# Talk

**Talk** is a push-to-talk voice input tool for Windows. It captures whispered (or normal) speech through a headset microphone, transcribes it via an online API or a local Whisper model, refines the text through an LLM, and injects the result at your current cursor position — all with a single hotkey.

**Talk** 是一个 Windows 上的按键说话语音输入工具。通过耳机麦克风捕捉低语（或正常）语音，使用在线 API 或本地 Whisper 模型进行转录，再通过 LLM 润色整理文本，最后将结果插入到当前光标位置——只需一个快捷键即可完成。

## Features / 功能

- **Push-to-Talk** — Hold F6 (configurable) to record, release to process.
  按住 F6（可配置）录音，松开后自动处理。
- **Two modes, auto-detected / 两种模式，自动检测：**
  - **Insert mode / 插入模式** — No text selected: voice input is cleaned up and inserted at the cursor.
    没有选中文字时，语音输入整理后插入到光标处。
  - **Polish mode / 润色模式** — Text selected: voice instruction is applied to modify the selected text.
    选中文字后，语音指令会被应用到选中的文字上进行修改。
- **Dual STT backends / 双语音识别后端：**
  - Online API (OpenAI-compatible, e.g. `gpt-4o-transcribe`)
    在线 API（OpenAI 兼容，如 `gpt-4o-transcribe`）
  - Local inference via [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
    本地推理（基于 faster-whisper）
- **LLM refinement / LLM 润色** — Any OpenAI-compatible API for text cleanup and polishing. Falls back to raw transcription if unconfigured.
  支持任何 OpenAI 兼容 API 进行文本整理润色。未配置时直接使用原始转录结果。
- **System tray UI / 系统托盘界面** — Status indicator with color-coded states + settings dialog.
  带颜色状态指示的系统托盘图标 + 设置对话框。
- **Whisper-optimized / 针对低语优化** — Configurable audio gain boost for whispered speech.
  可配置音频增益，针对低语场景优化。

## Requirements / 环境要求

- Windows 10/11
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended package manager)
- A working microphone
- An OpenAI-compatible STT API key (for online mode), or a GPU for local Whisper inference

## Installation / 安装

```bash
git clone https://github.com/jlmaoju/talk.git
cd talk
uv sync
```

## Usage / 使用

```bash
uv run talk
```

On first launch, a default config file is created at `~/.talk/config.toml`. You need to configure at least the STT API credentials (or switch to local mode) before using the app.

首次启动时会在 `~/.talk/config.toml` 创建默认配置文件。使用前至少需要配置 STT API 凭证（或切换为本地模式）。

Right-click the system tray icon to access **Settings** where you can configure:

右键系统托盘图标进入 **Settings** 可配置：

- Hotkey trigger / 快捷键
- STT backend (API or local) / 语音识别后端（API 或本地）
- LLM API credentials and model / LLM API 凭证和模型
- Audio gain boost / 音频增益

### Quick Start / 快速开始

1. Launch the app — a green circle appears in the system tray.
   启动应用——系统托盘出现绿色圆点。
2. Right-click tray icon → **Settings** → fill in your API keys.
   右键托盘图标 → **Settings** → 填入 API 密钥。
3. Click in any text field, hold **F6**, speak, release **F6**.
   在任意输入框中点击，按住 **F6**，说话，松开 **F6**。
4. Your speech is transcribed, refined, and inserted at the cursor.
   语音会被转录、整理，然后插入到光标位置。

## Configuration / 配置

Settings are stored in `~/.talk/config.toml`:

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `hotkey` | `trigger` | `f6` | Push-to-talk hotkey |
| `audio` | `gain_boost` | `3.0` | Gain multiplier for whispered speech |
| `stt` | `backend` | `api` | `api` or `local` |
| `stt` | `api_base_url` | `""` | OpenAI-compatible STT API endpoint |
| `stt` | `api_key` | `""` | STT API key |
| `stt` | `api_model` | `gpt-4o-transcribe` | STT model name |
| `stt` | `model_size` | `small` | Local Whisper model size |
| `llm` | `base_url` | `""` | OpenAI-compatible chat API endpoint |
| `llm` | `api_key` | `""` | LLM API key |
| `llm` | `model` | `""` | LLM model name |

## Development / 开发

```bash
uv run ruff check src/      # Lint
uv run ruff format src/      # Format
uv run pytest                # Run tests
```

## License / 许可证

This project is licensed under the [GNU General Public License v3.0](LICENSE).

本项目采用 [GNU 通用公共许可证 v3.0](LICENSE) 授权。
