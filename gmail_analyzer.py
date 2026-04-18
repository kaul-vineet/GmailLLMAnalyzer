#!/usr/bin/env python3
"""Search Gmail by content keyword and generate a chronological text report."""

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
    """Recursively extract plain-text body from MIME payload."""
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


def generate_report(emails, query, output_file):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "=" * 72,
        "  GMAIL EMAIL REPORT",
        f"  Query     : {query}",
        f"  Generated : {now}",
        f"  Results   : {len(emails)} emails (chronological)",
        "=" * 72,
    ]

    current_month = None

    for i, e in enumerate(emails, 1):
        month_label = e["date"].strftime("%B %Y") if e["date"] != datetime.min else "Unknown Date"

        if month_label != current_month:
            current_month = month_label
            lines += ["", f"  ── {month_label} " + "─" * (50 - len(month_label))]

        date_fmt = e["date"].strftime("%Y-%m-%d  %H:%M") if e["date"] != datetime.min else "Unknown"
        lines += [
            "",
            f"[{i}]  {date_fmt}",
            f"  From    : {e['from']}",
        ]
        if e["to"]:
            lines.append(f"  To      : {e['to']}")
        if e["cc"]:
            lines.append(f"  Cc      : {e['cc']}")
        lines.append(f"  Subject : {e['subject']}")
        lines.append("  " + "-" * 68)

        body = e["body"]
        if body:
            if len(body) > 3000:
                body = body[:3000] + "\n  … [truncated — full body exceeds 3000 chars]"
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
        description="Search Gmail by content and produce a chronological text report."
    )
    parser.add_argument("query", help='Search term, e.g. "budget approval" or "from:boss@acme.com invoice"')
    parser.add_argument("--max", type=int, default=100, help="Max emails to fetch (default 100)")
    parser.add_argument("--after", help="Emails after date  YYYY/MM/DD, e.g. 2024/01/01")
    parser.add_argument("--before", help="Emails before date YYYY/MM/DD, e.g. 2024/12/31")
    parser.add_argument("--output", "-o", help="Output filename (default: report_<query>.txt)")
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

    print(f"Generating report for {len(emails)} emails...")
    path = generate_report(emails, query, output)
    print(f"Report saved → {path}")


if __name__ == "__main__":
    main()
