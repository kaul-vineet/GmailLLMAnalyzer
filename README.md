# GmailLLMAnalyzer

Search your Gmail by keyword and get an AI-powered chronological analysis of what happened — decisions made, people involved, action items, and current status. Works with any LLM provider.

---

## What it does

1. Searches your Gmail using any query (keyword, sender, date range)
2. Fetches matching emails via the Gmail API
3. Sends them to an LLM — latest email first for context, then traces back chronologically
4. Produces a **text report** with:
   - AI narrative analysis (what happened, who did what, open items)
   - Raw email history (chronological, full bodies)

---

## Supported LLM Providers

| Provider | Model example | API key env var |
|---|---|---|
| Anthropic Claude | `anthropic/claude-opus-4-7` *(default)* | `ANTHROPIC_API_KEY` |
| Azure OpenAI | `azure/<your-deployment>` | `AZURE_API_KEY` + `AZURE_API_BASE` + `AZURE_API_VERSION` |
| OpenAI | `openai/gpt-4o` | `OPENAI_API_KEY` |
| Google Gemini | `gemini/gemini-1.5-pro` | `GEMINI_API_KEY` |

Any [LiteLLM-supported provider](https://docs.litellm.ai/docs/providers) works.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Google Cloud — Gmail API credentials

You need a `credentials.json` file to let the script access your Gmail.

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project (or select an existing one)
3. **APIs & Services → Enable APIs** → search for and enable **Gmail API**
4. **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
   - Application type: **Desktop App**
5. Download the JSON file and rename it to `credentials.json`
6. Place `credentials.json` in the same folder as `gmail_analyzer.py`
7. **APIs & Services → OAuth consent screen → Test users** → add your Gmail address

On first run, a browser window will open asking you to sign in and grant access. This creates a `token.json` file for future runs.

### 3. Set your LLM API key

```bash
# Windows
set ANTHROPIC_API_KEY=sk-ant-...

# Mac / Linux
export ANTHROPIC_API_KEY=sk-ant-...
```

See the [Supported LLM Providers](#supported-llm-providers) table for other providers.

---

## Usage

```bash
python gmail_analyzer.py "your search query" [options]
```

### Options

| Flag | Description |
|---|---|
| `--max N` | Max emails to fetch (default: 100) |
| `--after YYYY/MM/DD` | Only emails after this date |
| `--before YYYY/MM/DD` | Only emails before this date |
| `--model MODEL` | LLM model string (default: `anthropic/claude-opus-4-7`) |
| `--output FILE` | Output filename (default: `report_<query>.txt`) |
| `--no-ai` | Skip AI analysis, raw email report only |

### Examples

```bash
# Search by keyword, use default model (Claude)
python gmail_analyzer.py "budget approval"

# Search with date range
python gmail_analyzer.py "project renewal" --after 2024/01/01 --before 2024/12/31

# Use Azure OpenAI
set AZURE_API_KEY=...
set AZURE_API_BASE=https://your-resource.openai.azure.com/
set AZURE_API_VERSION=2024-02-01
python gmail_analyzer.py "vendor contract" --model azure/gpt-4o

# Use OpenAI GPT-4
set OPENAI_API_KEY=sk-...
python gmail_analyzer.py "onboarding" --model openai/gpt-4o

# Raw report only (no LLM call)
python gmail_analyzer.py "invoice" --no-ai

# Custom output file
python gmail_analyzer.py "Walmart" --max 200 --output walmart_history.txt
```

---

## Report structure

```
═══════════════════════════════════════════════════════
  GMAIL EMAIL ANALYSIS REPORT
  Query     : budget approval
  Model     : anthropic/claude-opus-4-7
  Generated : 2026-04-18 14:30
  Emails    : 12
═══════════════════════════════════════════════════════

  AI ANALYSIS
  ─────────────────────────────────────────────────────

  ## How it started
  ...chronological narrative...

  ## Key decisions
  ...

  ## Current status & open items
  ...

═══════════════════════════════════════════════════════

  RAW EMAIL HISTORY (chronological)
  ─────────────────────────────────────────────────────

  ── January 2024 ──────────────────────────────────

[1]  2024-01-05  09:14
  From    : alice@company.com
  To      : bob@company.com
  Subject : Budget request Q1
  ...
```

---

## Files

| File | Purpose |
|---|---|
| `gmail_analyzer.py` | Main script |
| `requirements.txt` | Python dependencies |
| `credentials.json` | Gmail OAuth credentials *(you provide, not committed)* |
| `token.json` | Gmail auth token *(auto-generated, not committed)* |
| `report_*.txt` | Generated reports *(not committed)* |

---

## Security

- `credentials.json` and `token.json` are in `.gitignore` and will never be committed
- Generated report files (`report_*.txt`) are also excluded from git
- The script requests **read-only** Gmail access (`gmail.readonly` scope)

---

## Requirements

- Python 3.8+
- A Google account with Gmail
- An API key for your chosen LLM provider
