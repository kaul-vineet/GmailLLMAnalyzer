#!/usr/bin/env python3
"""Search Gmail by content keyword and generate an LLM-powered chronological analysis report.

Supported providers (via LiteLLM):
  anthropic   → model: "anthropic/claude-opus-4-7"   | env: ANTHROPIC_API_KEY
  azure       → model: "azure/<deployment-name>"      | env: AZURE_API_KEY, AZURE_API_BASE, AZURE_API_VERSION
  openai      → model: "openai/gpt-4o"               | env: OPENAI_API_KEY
  gemini      → model: "gemini/gemini-1.5-pro"       | env: GEMINI_API_KEY
  any other LiteLLM-supported provider works the same way.
"""

import os
import sys
import base64
import argparse
from datetime import datetime
from email.utils import parsedate_to_datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import litellm

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

DEFAULT_MODEL = "anthropic/claude-opus-4-7"

SYSTEM_PROMPT = (
    "You are an expert email analyst. You receive a set of emails related to a topic "
    "and produce a clear, readable chronological history of what happened. "
    "Your analysis must:\n"
    "1. Start by reading the latest email to understand the current state\n"
    "2. Trace back to the beginning to understand how things started\n"
    "3. Present a CHRONOLOGICAL narrative (oldest to newest) of key events\n"
    "4. Highlight: decisions made, people involved, action items, escalations, outcomes\n"
    "5. End with a current status summary and any open items\n"
    "Write in clear prose. Use short section headers. Be concise but complete."
)


def authenticate():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists("credentials.json"):
                print("ERROR: credentials.json not found in current directory.")
                print("Steps to get it:")
                print("  1. Go to https://console.cloud.google.com")
                print("  2. Create project > Enable Gmail API")
                print("  3. Credentials > Create > OAuth 2.0 Client ID > Desktop App")
                print("  4. Download JSON and rename to credentials.json")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def extract_body(payload):
    mime = payload.get("mimeType", "")

    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace").strip()

    if mime.startswith("multipart"):
        for part in payload.get("parts", []):
            text = extract_body(part)
            if text:
                return text

    return ""


def parse_date(date_str):
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return datetime.min


def fetch_emails(service, query, max_results):
    emails = []
    page_token = None
    total_fetched = 0

    print(f"Searching: '{query}'")

    while total_fetched < max_results:
        batch = min(50, max_results - total_fetched)
        kwargs = {"userId": "me", "q": query, "maxResults": batch}
        if page_token:
            kwargs["pageToken"] = page_token

        result = service.users().messages().list(**kwargs).execute()
        messages = result.get("messages", [])
        if not messages:
            break

        for msg in messages:
            full = service.users().messages().get(
                userId="me", id=msg["id"], format="full"
            ).execute()

            headers = {h["name"]: h["value"] for h in full["payload"].get("headers", [])}

            emails.append({
                "date": parse_date(headers.get("Date", "")),
                "from": headers.get("From", "Unknown"),
                "to": headers.get("To", ""),
                "cc": headers.get("Cc", ""),
                "subject": headers.get("Subject", "(no subject)"),
                "body": extract_body(full["payload"]),
            })
            total_fetched += 1
            print(f"\r  Fetched {total_fetched} / {max_results}", end="", flush=True)

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    print()
    return sorted(emails, key=lambda e: e["date"])


def format_emails_for_llm(emails):
    """Format emails latest-first so the LLM reads current state before tracing history."""
    lines = []
    for i, e in enumerate(reversed(emails), 1):
        date_fmt = e["date"].strftime("%Y-%m-%d %H:%M") if e["date"] != datetime.min else "Unknown"
        body = e["body"][:2000] + "…" if len(e["body"]) > 2000 else e["body"]
        lines.append(
            f"--- EMAIL {i} (latest first) ---\n"
            f"Date   : {date_fmt}\n"
            f"From   : {e['from']}\n"
            f"To     : {e['to']}\n"
            f"CC     : {e['cc']}\n"
            f"Subject: {e['subject']}\n"
            f"Body:\n{body or '(no body)'}\n"
        )
    return "\n".join(lines)


def analyse_with_llm(emails, query, model):
    """Send emails to any LiteLLM-supported model and stream back a chronological analysis."""
    email_block = format_emails_for_llm(emails)

    user_content = (
        f'Search query used: "{query}"\n'
        f"Total emails found: {len(emails)}\n\n"
        f"Here are the emails (shown latest-first so you can understand current state first):\n\n"
        f"{email_block}"
    )

    print(f"Sending to {model} for analysis...")

    try:
        response = litellm.completion(
            model=model,
            max_tokens=4096,
            stream=True,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_content},
            ],
        )
    except Exception as e:
        print(f"\nERROR calling LLM: {e}")
        print("Check your API key env vars and model string.")
        return None

    analysis = ""
    for chunk in response:
        delta = chunk.choices[0].delta.content or ""
        print(delta, end="", flush=True)
        analysis += delta

    print("\n")
    return analysis


def generate_report(emails, query, model, analysis, output_file):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "=" * 72,
        "  GMAIL EMAIL ANALYSIS REPORT",
        f"  Query     : {query}",
        f"  Model     : {model}",
        f"  Generated : {now}",
        f"  Emails    : {len(emails)}",
        "=" * 72,
    ]

    if analysis:
        lines += ["", "  AI ANALYSIS", "  " + "─" * 68, ""]
        for line in analysis.splitlines():
            lines.append("  " + line)
        lines += ["", "=" * 72]

    lines += ["", "  RAW EMAIL HISTORY (chronological)", "  " + "─" * 68]

    current_month = None
    for i, e in enumerate(emails, 1):
        month_label = e["date"].strftime("%B %Y") if e["date"] != datetime.min else "Unknown Date"

        if month_label != current_month:
            current_month = month_label
            lines += ["", f"  ── {month_label} " + "─" * max(1, 50 - len(month_label))]

        date_fmt = e["date"].strftime("%Y-%m-%d  %H:%M") if e["date"] != datetime.min else "Unknown"
        lines += ["", f"[{i}]  {date_fmt}", f"  From    : {e['from']}"]
        if e["to"]:
            lines.append(f"  To      : {e['to']}")
        if e["cc"]:
            lines.append(f"  Cc      : {e['cc']}")
        lines.append(f"  Subject : {e['subject']}")
        lines.append("  " + "-" * 68)

        body = e["body"]
        if body:
            if len(body) > 3000:
                body = body[:3000] + "\n  … [truncated]"
            for line in body.splitlines():
                lines.append("  " + line)
        else:
            lines.append("  (no plain-text body)")

    lines += [
        "",
        "=" * 72,
        f"  END OF REPORT — {len(emails)} emails matched '{query}'",
        "=" * 72,
    ]

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Search Gmail by content and produce an LLM-powered chronological analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Model examples:
  anthropic/claude-opus-4-7       (default) — needs ANTHROPIC_API_KEY
  azure/gpt-4o                              — needs AZURE_API_KEY, AZURE_API_BASE, AZURE_API_VERSION
  openai/gpt-4o                             — needs OPENAI_API_KEY
  gemini/gemini-1.5-pro                     — needs GEMINI_API_KEY
        """,
    )
    parser.add_argument("query", help='Search term, e.g. "budget approval"')
    parser.add_argument("--max", type=int, default=100, help="Max emails to fetch (default 100)")
    parser.add_argument("--after",  help="Emails after date  YYYY/MM/DD")
    parser.add_argument("--before", help="Emails before date YYYY/MM/DD")
    parser.add_argument("--output", "-o", help="Output filename")
    parser.add_argument("--model",  "-m", default=DEFAULT_MODEL, help=f"LLM model string (default: {DEFAULT_MODEL})")
    parser.add_argument("--no-ai",  action="store_true", help="Skip AI analysis, raw report only")
    args = parser.parse_args()

    query = args.query
    if args.after:
        query += f" after:{args.after}"
    if args.before:
        query += f" before:{args.before}"

    output = args.output or "report_" + args.query[:40].replace(" ", "_").replace("/", "-") + ".txt"

    service = authenticate()
    emails = fetch_emails(service, query, args.max)

    if not emails:
        print("No emails found for that query.")
        return

    analysis = None
    if not args.no_ai:
        analysis = analyse_with_llm(emails, query, args.model)

    print(f"Generating report...")
    path = generate_report(emails, query, args.model, analysis, output)
    print(f"Report saved → {path}")


if __name__ == "__main__":
    main()
