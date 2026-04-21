# `app/ai/` — AI Provider Abstraction

Minimal adapter layer between the node and any OpenAI-compatible chat-completions endpoint. Used by:

- `app/chats/ai_assistant.py` — in-chat "/ai" assistant.
- `app/chats/translate.py` — on-demand message translation.
- `app/bots/bot_advanced.py` — AI-powered bot helpers.

The node never ships its own model. This module only wraps a remote HTTP API; the operator provides the URL + key.

## Files

| File          | Role                                                                          |
| ------------- | ----------------------------------------------------------------------------- |
| `provider.py` | Single-class adapter. Reads `AI_PROVIDER_URL` + `AI_PROVIDER_KEY` from config. Exposes `async chat(messages, model=None, stream=False)`. |

## Supported backends

Anything that speaks the OpenAI Chat Completions wire format — `POST /v1/chat/completions` with `{model, messages, stream}`:

- OpenAI (`api.openai.com`)
- Azure OpenAI (set `AI_PROVIDER_URL` to the deployment URL)
- Self-hosted **Qwen3-8B** (see `../../Qwen3-8B/`) via vLLM / llama.cpp `--api-like` mode
- Any other OpenAI-clone (LM Studio, Ollama with the OpenAI compatibility shim, llama-cpp-python server)

## Configuration

| Env var             | Purpose                                              |
| ------------------- | ---------------------------------------------------- |
| `AI_PROVIDER_URL`   | Base URL — e.g. `https://api.openai.com/v1/`.        |
| `AI_PROVIDER_KEY`   | Bearer token. Optional for local backends.           |
| `AI_DEFAULT_MODEL`  | Model name when the caller doesn't specify (e.g. `gpt-4o-mini`, `qwen3-8b`). |
| `AI_TIMEOUT_SECS`   | Per-call timeout (default 30).                        |

If `AI_PROVIDER_URL` is empty, AI features are disabled at startup — the "/ai" assistant route returns 503 and bots get a clear error instead of a timeout.

## Why it's minimal

The whole file is <200 lines on purpose. Providers churn faster than Vortex's release cadence; keeping the abstraction thin means we can swap backends without touching feature code.

---

## License

Vortex is released under the **Apache License 2.0**.

```
Copyright 2026 Andrey Karavaev, Boris Maltsev

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

---

## Authors

**Boris Maltsev**

[![GitHub](https://img.shields.io/badge/GitHub-BorisMalts-181717?style=flat-square&logo=github)](https://github.com/BorisMalts)

**Andrey Karavaev**

[![GitHub](https://img.shields.io/badge/GitHub-Andre--wb-181717?style=flat-square&logo=github)](https://github.com/Andre-wb)
