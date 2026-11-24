#!/usr/bin/env python3
"""Bulk-create email templates in notification-service via POST /api/v1/templates.

Reads a CSV with the columns of the email_templates table
(id, body, created_at, description, html_enabled, name, subject, updated_at) and
creates one template per row. The `id` column is ignored: the service generates the UUID.

Outcomes per template:
  CREATED  201 returned
  SKIPPED  409 returned (a template with that name already exists)
  FAILED   anything else (validation error, 4xx/5xx, network error after retries)

Logs (in --log-dir, default ./logs):
  upload_<timestamp>.log    everything shown on screen, with timestamps
  failures_<timestamp>.log  only the failed templates, with HTTP status and response body
Exit code is 1 if any template failed, otherwise 0. Standard library only.

Example:
  python3 upload_templates.py --header "Authorization: Bearer <token>"
  python3 upload_templates.py --dry-run
  python3 upload_templates.py --csv other_templates.csv --dry-run   # use a different file

The target is the single BASE_URL key near the top of this script (scheme, host AND port,
e.g. "http://localhost:8080"). Before sending anything the script prints it and asks you to confirm.

By default the templates are read from sourceData/email_templates_final.csv next to this script.
"""
import argparse
import csv
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

# >>> The ONE key holding the target base URL, including the port. Edit it here. <<<
BASE_URL = "http://localhost:8080"

NAME_RE = re.compile(r"^[a-z0-9-]+$")
ENDPOINT = "/api/v1/templates"
DEFAULT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sourceData", "email_templates_final.csv")


def build_logger(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_log = os.path.join(log_dir, f"upload_{stamp}.log")
    fail_log = os.path.join(log_dir, f"failures_{stamp}.log")

    log = logging.getLogger("upload")
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(run_log, encoding="utf-8")
    fh.setFormatter(fmt)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(fh)
    log.addHandler(console)

    fail = logging.getLogger("upload.failures")
    ff = logging.FileHandler(fail_log, encoding="utf-8", delay=True)  # created on first failure
    ff.setFormatter(fmt)
    fail.addHandler(ff)
    return log, fail, run_log, fail_log


def read_rows(path):
    csv.field_size_limit(10 ** 9)
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def to_payload(row):
    return {
        "name": row["name"],
        "subject": row["subject"],
        "body": row["body"],
        "description": row.get("description") or None,
        "htmlEnabled": str(row.get("html_enabled", "true")).strip().lower() == "true",
    }


def validate(p):
    """Same rules as EmailTemplateRequest, so problems show up before any request is sent."""
    errs = []
    if not p["name"] or len(p["name"]) > 100 or not NAME_RE.match(p["name"]):
        errs.append("name must be lowercase alphanumeric with hyphens, max 100 chars")
    if not p["subject"] or len(p["subject"]) > 500:
        errs.append("subject is required, max 500 chars")
    if not p["body"]:
        errs.append("body is required")
    if p["description"] and len(p["description"]) > 500:
        errs.append("description max 500 chars")
    return errs


def post(url, payload, headers, timeout):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def post_with_retries(url, payload, headers, timeout, retries):
    """Retry on network errors and 5xx; 4xx are final."""
    attempt = 0
    while True:
        attempt += 1
        try:
            status, body = post(url, payload, headers, timeout)
            if status < 500 or attempt > retries:
                return status, body
            err = f"HTTP {status}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            if attempt > retries:
                return None, f"{type(e).__name__}: {e}"
            err = f"{type(e).__name__}: {e}"
        time.sleep(min(2 ** attempt, 10))
        logging.getLogger("upload").debug("retrying %s (attempt %d) after %s", payload["name"], attempt + 1, err)


def parse_headers(items):
    headers = {}
    for item in items or []:
        if ":" not in item:
            sys.exit(f"Invalid --header '{item}', expected 'Name: value'")
        k, v = item.split(":", 1)
        headers[k.strip()] = v.strip()
    return headers


def confirm_base_url(base_url):
    """Show the base URL and require an explicit yes before any API call is made."""
    print(f"Base URL: {base_url}")
    answer = input("Are you sure you want to run the script on this base url? [y/N]: ").strip().lower()
    if answer not in ("y", "yes"):
        sys.exit("Aborted. Update the key BASE_URL in this script (%s) and run again." % os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=DEFAULT_CSV,
                    help=f"CSV file with the email_templates columns (default: {DEFAULT_CSV})")
    ap.add_argument("--header", action="append", help="extra request header 'Name: value' (repeatable)")
    ap.add_argument("--timeout", type=int, default=60, help="per-request timeout in seconds (default 60)")
    ap.add_argument("--retries", type=int, default=2, help="retries on network errors / 5xx (default 2)")
    ap.add_argument("--log-dir", default="logs", help="directory for log files (default ./logs)")
    ap.add_argument("--dry-run", action="store_true", help="read and validate the CSV, send nothing")
    args = ap.parse_args()

    confirm_base_url(BASE_URL)

    log, fail_log_, run_log, fail_log = build_logger(args.log_dir)
    rows = read_rows(args.csv)
    total = len(rows)
    url = BASE_URL.rstrip("/") + ENDPOINT
    headers = parse_headers(args.header)

    log.info("Source : %s (%d templates)", args.csv, total)
    log.info("Target : %s%s", url if not args.dry_run else "(dry run, nothing will be sent)", "")
    log.info("-" * 78)

    counts = {"CREATED": 0, "SKIPPED": 0, "FAILED": 0}
    failed = []
    started = time.time()

    for i, row in enumerate(rows, 1):
        payload = to_payload(row)
        name = payload["name"]
        pct = int(i * 100 / total)
        prefix = f"[{i:>{len(str(total))}}/{total}] {pct:>3}%"

        errs = validate(payload)
        if errs:
            outcome, detail = "FAILED", "validation: " + "; ".join(errs)
            fail_log_.error("%s | %s", name, detail)
        elif args.dry_run:
            outcome, detail = "CREATED", "dry run, valid"
        else:
            t0 = time.time()
            status, resp = post_with_retries(url, payload, headers, args.timeout, args.retries)
            took = time.time() - t0
            if status == 201:
                outcome, detail = "CREATED", f"201 in {took:.2f}s"
            elif status == 409:
                outcome, detail = "SKIPPED", "409 already exists"
            else:
                outcome = "FAILED"
                detail = f"{status if status is not None else 'no response'} in {took:.2f}s"
                fail_log_.error("%s | status=%s | payload_chars=%d | response=%s",
                                name, status, len(payload["body"]), resp[:2000])
                log.debug("response for %s: %s", name, resp[:2000])

        counts[outcome] += 1
        if outcome == "FAILED":
            failed.append(name)
        log.info("%s  %-7s %s  (%s)", prefix, outcome, name, detail)

    log.info("-" * 78)
    log.info("Done in %.1fs: %d created, %d skipped (already exist), %d failed",
             time.time() - started, counts["CREATED"], counts["SKIPPED"], counts["FAILED"])
    if failed:
        log.info("Failed templates:")
        for n in failed:
            log.info("  - %s", n)
        log.info("Failure details: %s", fail_log)
    log.info("Full log: %s", run_log)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
