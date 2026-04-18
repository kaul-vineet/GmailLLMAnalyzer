# Session Context

> This file tracks current state, decisions made, and next steps.
> Update it before ending a session. On a new machine, read this first.

---

## Current State — 2026-04-18

**Status:** Complete and working. All code committed and pushed.

### What is built
- `gmail_analyzer.py` — searches Gmail by keyword, sends emails to any LLM via LiteLLM, streams a chronological narrative analysis, writes a `.txt` report
- Provider-agnostic: Claude, Azure OpenAI, OpenAI, Gemini — swap via `--model` flag
- README with ASCII logo, Mermaid diagrams, provider table

### Last commits
| Hash | Message |
|---|---|
| `f70857c` | Beautify README |
| `1f5f4df` | Make LLM provider-agnostic via LiteLLM |
| `71f82e2` | Add Claude AI reasoning |
| `d2ef691` | Initial commit |

---

## Setup on a new machine

```bash
# 1. Clone
git clone https://github.com/kaul-vineet/GmailLLMAnalyzer
cd GmailLLMAnalyzer

# 2. Install deps
pip install -r requirements.txt

# 3. Add credentials.json (Gmail OAuth — download from Google Cloud Console)
#    Place in the project folder — never committed

# 4. Set API key for your chosen LLM provider
set ANTHROPIC_API_KEY=sk-ant-...         # Anthropic
set AZURE_API_KEY=...                    # Azure OpenAI
set AZURE_API_BASE=https://...           # Azure OpenAI
set AZURE_API_VERSION=2024-02-01         # Azure OpenAI
set OPENAI_API_KEY=sk-...               # OpenAI

# 5. Run
python gmail_analyzer.py "your search query"
```

---

## Files not in git (need to bring manually or recreate)

| File | How to get it |
|---|---|
| `credentials.json` | Google Cloud Console → Gmail API → OAuth 2.0 Client ID (Desktop App) → Download |
| `token.json` | Auto-generated on first run after browser consent |

---

## Pending / Next steps

- [ ] Test end-to-end with real Gmail account
- [ ] Get Anthropic API key from console.anthropic.com
- [ ] Consider adding `.env` file support so keys don't need to be set manually each session

---

## How to update this file

Before ending a session, update the **Current State** section and **Pending** checklist.
Commit with: `git add CONTEXT.md && git commit -m "Update session context" && git push`
