#!/usr/bin/env python3
"""Search Gmail by content keyword and generate a Claude-powered chronological analysis report."""

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
import anthropic

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


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


def format_emails_for_claude(emails):
    """Format emails into a structured block for Claude — latest first for context, then chronological."""
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


def analyse_with_claude(emails, query):
    """Send emails to Claude and get a chronological narrative analysis."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("WARNING: ANTHROPIC_API_KEY not set — skipping AI analysis.")
        return None

    client = anthropic.Anthropic(api_key=api_key)

    email_block = format_emails_for_claude(emails)

    system_prompt = (
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

    print("Sending to Claude for analysis (this may take a moment)...")

    with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Search query used: \"{query}\"\n"
                            f"Total emails found: {len(emails)}\n\n"
                            f"Here are the emails (shown latest-first so you can understand current state first):\n\n"
                            f"{email_block}"
                        ),
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            }
        ],
    ) as stream:
        analysis = ""
        for text in stream.text_stream:
            print(text, end="", flush=True)
            analysis += text

    print("\n")

    final = stream.get_final_message()
    usage = final.usage
    print(
        f"  Tokens — input: {usage.input_tokens} | "
        f"cached: {usage.cache_read_input_tokens} | "
        f"output: {usage.output_tokens}"
    )

    return analysis


def generate_report(emails, query, analysis, output_file):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "=" * 72,
        "  GMAIL EMAIL ANALYSIS REPORT",
        f"  Query     : {query}",
        f"  Generated : {now}",
        f"  Emails    : {len(emails)}",
        "=" * 72,
    ]

    if analysis:
        lines += [
            "",
            "  CLAUDE AI ANALYSIS",
            "  " + "─" * 68,
            "",
        ]
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
        description="Search Gmail by content and produce a Claude-powered chronological analysis."
    )
    parser.add_argument("query", help='Search term, e.g. "budget approval" or "from:boss@acme.com invoice"')
    parser.add_argument("--max", type=int, default=100, help="Max emails to fetch (default 100)")
    parser.add_argument("--after", help="Emails after date YYYY/MM/DD")
    parser.add_argument("--before", help="Emails before date YYYY/MM/DD")
    parser.add_argument("--output", "-o", help="Output filename (default: report_<query>.txt)")
    parser.add_argument("--no-ai", action="store_true", help="Skip Claude analysis, raw report only")
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
        analysis = analyse_with_claude(emails, query)

    print(f"Generating report for {len(emails)} emails...")
    path = generate_report(emails, query, analysis, output)
    print(f"Report saved → {path}")


if __name__ == "__main__":
    main()
