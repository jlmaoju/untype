# UnType (忘言)

> 得意忘言 — Speak your mind, forget about typing.

**UnType** is an open-source, AI-powered voice input tool for Windows. It doesn't just transcribe — it **thinks**. Your speech goes through STT, then an LLM automatically cleans up the text: fixing punctuation, removing filler words, correcting recognition errors. Select existing text and speak to edit it with natural language. One hotkey does it all.

**UnType** 是一个开源的 AI 语音输入工具。它不只是转录——它会**思考**。语音经过 STT 转录后，LLM 自动润色文本：修正标点、去除语气词、纠正识别错误。选中已有文字后说话，即可用自然语言编辑它。一个快捷键，从说话到成稿。

## Why UnType? / 为什么选 UnType？

Most voice input tools give you raw transcription — full of "嗯", "那个", broken punctuation, and recognition errors. You end up spending time fixing what was supposed to save you time.

大多数语音输入工具只给你原始转录——充满"嗯"、"那个"、标点错误和识别偏差。你最终花在修正上的时间，比省下的打字时间还多。

**UnType = STT + LLM.** Your speech is transcribed, then an LLM refines it into clean, well-formatted text — ready to use as-is.

**UnType = STT + LLM。** 语音先转录，再由 LLM 润色为干净、规范的文本——开口即终稿。

**And it goes further:** select text, speak an instruction, and UnType rewrites it for you. "把这段改得更正式一点" — done.

**更进一步：** 选中文字，说出修改指令，UnType 帮你改写。"把这段改得更正式一点"——搞定。

## Features / 功能

- **AI-refined output / AI 润色输出** — Not raw transcription. LLM automatically fixes punctuation, filler words, grammar, and recognition errors before text reaches your cursor.
  不是原始转录。LLM 在文本到达光标前，自动修正标点、语气词、语法和识别错误。
- **Voice-edit selected text / 语音编辑选中文字** — Select text, speak an instruction ("make it shorter", "translate to English", "改成被动语态"), and the LLM applies it. Like a voice-controlled find-and-replace on steroids.
  选中文字，说出指令，LLM 执行修改。语音版的超级查找替换。
- **Push-to-Talk** — Hold a hotkey (default: F6) to record, release to process. Works in any application.
  按住快捷键（默认 F6）录音，松开后处理。在任何应用中都能用。
- **Dual STT backends / 双语音识别后端** — Online API (OpenAI-compatible) or local inference via [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Your choice.
  在线 API（OpenAI 兼容）或本地推理（faster-whisper）。自由选择。
- **System tray UI / 系统托盘界面** — Color-coded status indicator + settings dialog.
  带颜色状态指示的托盘图标 + 设置对话框。

## How It Works / 工作原理

```
Hold hotkey → Speak → Release hotkey
                ↓
        [ STT: speech → raw text ]
                ↓
        [ LLM: raw text → polished text ]
                ↓
        Text appears at your cursor ✓
```

**Two modes, auto-detected:**

| Mode | Trigger | What happens |
|------|---------|-------------|
| **Insert** | No text selected | Speech → STT → LLM cleanup → insert at cursor |
| **Polish** | Text selected | Speech becomes an instruction → LLM modifies the selected text |

## Quick Start / 快速开始

```bash
git clone https://github.com/jlmaoju/untype.git
cd untype
uv sync
uv run untype
```

1. A green circle appears in the system tray. Right-click → **Settings** → fill in your API keys.
   系统托盘出现绿色圆点。右键 → **Settings** → 填入 API 密钥。
2. Click in any text field, hold **F6**, speak, release **F6**.
   在任意输入框中点击，按住 **F6**，说话，松开 **F6**。
3. Polished text appears at your cursor.
   润色好的文字出现在光标处。

## Requirements / 环境要求

- Windows 10/11
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended package manager)
- A working microphone
- An OpenAI-compatible STT API key (for online mode), or a GPU for local Whisper inference
- An OpenAI-compatible LLM API key (for text refinement; optional but recommended)

## Configuration / 配置

Settings are stored in `~/.untype/config.toml` (created on first launch):

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `hotkey` | `trigger` | `f6` | Push-to-talk hotkey |
| `audio` | `gain_boost` | `3.0` | Gain multiplier for quiet speech |
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
