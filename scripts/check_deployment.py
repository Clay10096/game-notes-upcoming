#!/usr/bin/env python3
"""Validate Cloudflare Pages settings without displaying credentials."""
import os
import re

if os.getenv("HOSTING_PROVIDER") != "cloudflare":
    raise SystemExit("Set HOSTING_PROVIDER=cloudflare in GitHub Actions variables")
if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", os.getenv("CLOUDFLARE_PAGES_PROJECT", "")):
    raise SystemExit("Set a valid CLOUDFLARE_PAGES_PROJECT repository variable")
for name in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"):
    if not os.getenv(name):
        raise SystemExit(f"Missing GitHub Actions secret: {name}")
print("Cloudflare Pages publishing configuration is present")
