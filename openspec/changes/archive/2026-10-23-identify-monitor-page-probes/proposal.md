# Identify the monitor's setup page check

## Why

The keyword precheck uses Ansible's `open_url` without an explicit `http_agent`.
A public page behind Cloudflare can refuse that request
with HTTP 403 / error 1010 while accepting the same client with an honest
identifying User-Agent. This prevents a valid keyword monitor from being set up.

## What changes

- Send `Krot site monitor setup` as the User-Agent of the keyword page precheck
- Keep TLS verification, redirect following, timeout, case-sensitive matching,
  and refusal before any monitor write when the page is unreadable or lacks the word
- Verify the header through the real Ansible HTTP client against a local server,
  including redirects and HTTP failures

The precheck identifies its own setup request; it does not configure the
User-Agent of UptimeRobot's subsequent checks or change site protection.
