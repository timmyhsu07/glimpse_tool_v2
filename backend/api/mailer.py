"""Sends the password-reset email.

Uses Resend (https://resend.com) when RESEND_API_KEY and MAIL_FROM are set.
Without them, a local server prints the link to its console so the flow can be
tested; on Vercel, reset by email is reported as not set up.
"""
import json
import os
import sys
import urllib.request


def configured():
    return bool(os.environ.get("RESEND_API_KEY") and os.environ.get("MAIL_FROM"))


def available():
    return configured() or not os.environ.get("VERCEL")


def send_reset(email, link):
    text = (f"Someone asked to reset the password for your GLIMPSE account.\n\n"
            f"Set a new password here (the link works once, for 1 hour):\n{link}\n\n"
            f"If this wasn't you, ignore this email. Your password stays the same.")
    if not configured():
        print(f"[glimpse] password reset link for {email}: {link}", file=sys.stderr, flush=True)
        return
    body = json.dumps({"from": os.environ["MAIL_FROM"], "to": [email],
                       "subject": "Reset your GLIMPSE password", "text": text}).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=body, method="POST",
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()
