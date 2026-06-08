# OpenCode Provider Authentication

## Overview

OpenCode 1.16+ bundles providers for common AI APIs internally using `@ai-sdk/*` packages. For DeepSeek specifically, it uses `@ai-sdk/openai-compatible` with native DeepSeek detection — NOT a generic OpenAI-compatible fallback.

## Available Providers

Check with: `opencode providers list`

## Adding Credentials

### Interactive (PTY Required)

```bash
opencode auth login
# or
opencode providers login -p openai -m "Manually enter API Key"
```

The interactive TUI (terminal selectors) requires `pty=true`. Note that piping input via `echo "key" | opencode providers login` will NOT work — the interactive terminal selectors consume stdin before the credential field is reached.

### Environment Variables (Headless Workaround)

OpenCode's `run` subcommand ignores shell environment variables like `DEEPSEEK_API_KEY` and `OPENAI_API_KEY` — it loads credentials exclusively from its internal SQLite store (opencode.db). However, the `serve` subcommand DOES check env vars during provider initialization.

**Workaround for headless/server environments** where interactive `opencode providers login` is impractical:

1. Set the env var and start `opencode serve`:
```bash
DEEPSEEK_API_KEY="sk-..." opencode serve --port 18123 --print-logs 2>&1
```

2. Verify the provider is enabled via env var:
```bash
curl -s -H "Accept: application/json" http://localhost:18123/api/provider/deepseek
# Expected: "enabled":{"via":"env","name":"DEEPSEEK_API_KEY"}
```

3. Use the web UI or REST API to interact:
```bash
# List sessions
curl -s -H "Accept: application/json" http://localhost:18123/api/session

# Open the web UI in a browser (if GUI available)
open http://localhost:18123
```

4. Check the provider's config details:
```bash
curl -s -H "Accept: application/json" http://localhost:18123/api/provider/deepseek | python3 -m json.tool
```

This works because the `serve` process initializes providers at startup, checking the process environment. The `run` subcommand creates a fresh short-lived process that doesn't perform the same env-var check.

**Note**: Once a credential is stored in the database via `opencode providers login`, `opencode run` will use that database credential. The serve-mode env var workaround is for environments where you can't run the interactive login.

### Model String Convention

Use `provider/model` format with `--model`:

```bash
opencode run 'Say OK' --model deepseek/deepseek-chat
opencode run 'Say OK' --model openrouter/anthropic/claude-sonnet-4
```

## Troubleshooting Auth

### 1. Test the API Key Independently

Before debugging OpenCode, verify the key works with the provider directly:

```bash
# DeepSeek
curl -s https://api.deepseek.com/models \
  -H "Authorization: Bearer sk-your-key-here" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(f'OK: {len(d.get(\"data\",[]))} models' if 'data' in d else d)"

# Expected: "OK: 63 models" (or similar count)
# 401 error means the key is invalid on the provider side
```

### 2. Check OpenCode Logs

OpenCode writes detailed logs including API request/response details:

```bash
ls -lt ~/.local/share/opencode/log/  # Most recent logs first
cat ~/.local/share/opencode/log/$(ls -t ~/.local/share/opencode/log/ | head -1)
```

Log lines contain:
- `providerID=deepseek found` — provider detected
- `llm.runtime=ai-sdk llm.provider=deepseek llm.model=deepseek-chat` — runtime selection
- `statusCode=401` — auth failure details
- Full request body and response headers

### 3. Check Models Available

```bash
opencode models deepseek
# Lists available models if auth is working
```

### 4. SQLite Event Inspection (Most Thorough)

When login/polling/logs aren't enough, inspect the event table directly:

```bash
python3 -c "
import sqlite3, json
conn = sqlite3.connect('$HOME/.local/share/opencode/opencode.db')

# Find the most recent API errors
cur = conn.execute(\"\"\"
  SELECT data FROM event
  WHERE type = 'message.updated.1'
  ORDER BY rowid DESC LIMIT 10
\"\"\")
for r in cur.fetchall():
    d = json.loads(r[0])
    info = d.get('info', {})
    if 'error' in info:
        err = info['error']
        print(f\"ERROR: {err.get('name')}\")
        print(f\"  Message: {err.get('data', {}).get('message','')[:100]}\")
        print(f\"  Status: {err.get('data', {}).get('statusCode','?')}\")
        print(f\"  URL: {err.get('data', {}).get('metadata', {}).get('url','')}\")

# Check which credential is stored
cur = conn.execute('SELECT email, url, access_token FROM account')
print('\\n--- Stored Accounts ---')
for r in cur.fetchall():
    print(f\"  Provider: {r[0]} URL: {r[1]} Key: {r[2][:8]}...{r[2][-4:]}\")
"
```

This shows:
- The exact API URL called (verify it's the right endpoint)
- The status code and response body from the provider
- **Which credential OpenCode is actually sending** (check if it matches your intended key)
- The account table content (what's stored in the DB)

### 5. Clear Session Database (Fresh Start)

If the database has stale credentials or many failed sessions, wipe it clean:

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('$HOME/.local/share/opencode/opencode.db')
for table in ['session_message', 'session', 'event', 'event_sequence', 'message', 'part', 'account']:
    conn.execute(f'DELETE FROM {table}')
conn.commit()
print('Cleaned')
"
```

Then run `opencode run` again with fresh state.

## SQLite Database Layout

OpenCode stores session data and credentials in SQLite at `~/.local/share/opencode/opencode.db`.

Key tables:
- `account` — provider credentials (access_token, url, email)
- `account_state` — which account is active
- `event` — audit log of all model calls (includes full API error responses)
- `session` — session metadata including provider/model used
- `workspace` — per-project workspaces and branches

## Common Provider Setup Commands

```bash
# List configured providers
opencode providers list
# or
opencode auth list

# Add provider via interactive login
opencode providers login

# Logout from a provider
opencode providers logout
```
