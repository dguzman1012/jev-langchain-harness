# Jev + LangChain agent harness (PoC)

Minimal proof of concept showing **Jev** (TypeSafe System One) as a **decision layer** on top of LangChain—not a chat UI.

- **Jev** (`TypeSafeClassifier`): typed judgments (Choice / Score / Noul) with calibrated probabilities.
- **LLM** (OpenAI via LangChain): text generation and tool selection inside `create_agent`.
- **Harness**: experimental middleware that calls Jev at agent lifecycle hooks (model routing, tool-risk gating).

Inspired by [Building a harness with Jev](https://www.langchain.com/blog/building-a-harness-with-jev) and the [LangChain TypeSafe integration](https://docs.langchain.com/oss/python/integrations/providers/typesafe). Jev product docs: [docs.typesafe.ai](https://docs.typesafe.ai).

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Install

```bash
cd /path/to/repo
uv sync
# or: pip install -e ".[experimental]"  # after adding a build backend if you prefer pip
```

With pip and no `uv`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install "langchain-typesafe[experimental]" langchain langchain-openai python-dotenv
```

## Environment

Copy `.env.example` to `.env` and set:

| Variable | Required | Purpose |
|----------|----------|---------|
| `TYPESAFE_API_KEY` | Yes | Jev / TypeSafe API (classifier + middleware) |
| `OPENAI_API_KEY` | No | Live `create_agent` run; omit to use harness `--dry-run` |

```bash
cp .env.example .env
export TYPESAFE_API_KEY="your-key"
# optional:
export OPENAI_API_KEY="sk-..."
```

## 1. Email triage classifier (primary happy path)

One `TypeSafeClassifier.invoke` answers four questions: category (Choice), urgency (Score), `needs_human` and `actionable` (Noul).

```bash
uv run python scripts/classify_email.py --sample outage
uv run python scripts/classify_email.py --sample billing
uv run python scripts/classify_email.py --sample spam
uv run python scripts/classify_email.py --sample sales
uv run python scripts/classify_email.py -f samples/urgent_outage.txt
uv run python scripts/classify_email.py "Quick question about my invoice"
```

Samples live in `samples/` (outage, billing, spam, calm sales).

## 2. Agent harness (middleware)

Demonstrates:

- `ModelRouterMiddleware` — Jev **Choice** between fast (`gpt-4o-mini`) and powerful (`gpt-4o`) models.
- `AutoModeMiddleware` — Jev **Noul** risk gate on `delete_all_backups`; `lookup_docs` is unlisted and runs without classification.

**Dry-run** (only `TYPESAFE_API_KEY`): runs the same Jev classifiers the middleware uses, prints route and whether the risky tool would be blocked—no OpenAI calls.

```bash
uv run python scripts/agent_harness.py --dry-run
uv run python scripts/agent_harness.py --dry-run -m "Look up the backup retention runbook"
```

**Full agent** (requires `OPENAI_API_KEY`):

```bash
uv run python scripts/agent_harness.py
uv run python scripts/agent_harness.py -m "Delete all backups now"
```

## Layout

```
scripts/
  classify_email.py   # CLI email triage with TypeSafeClassifier
  agent_harness.py    # create_agent + ModelRouter + AutoMode
samples/              # email fixtures
pyproject.toml
.env.example
```

## How it fits together

```mermaid
flowchart LR
  subgraph decisions [Jev decisions]
    C[TypeSafeClassifier]
  end
  subgraph agent [LangChain agent loop]
    M[ModelRouterMiddleware]
    A[create_agent LLM]
    T[AutoModeMiddleware]
    Tools[Tools]
  end
  User --> M
  M --> C
  M --> A
  A --> T
  T --> C
  T --> Tools
```

Middleware imports match `langchain-typesafe==0.0.1a2`:

```python
from langchain_typesafe.experimental.middleware import (
    AutoModeMiddleware,
    ModelChoice,
    ModelRouterMiddleware,
)
```

## License

MIT (PoC — use at your own risk).
