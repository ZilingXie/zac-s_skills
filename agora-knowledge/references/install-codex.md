# Codex (CLI / Desktop) MCP setup

Add to `~/.codex/config.toml`. The token lives in the `env` table and is
referenced with `${AGORA_TOKEN}` — `codex mcp list` prints `args` verbatim
but masks `env`, so this keeps the token out of terminal output.

Requires Node >= 18 for `npx`.

```toml
[mcp_servers."agora-knowledge"]
command = "npx"
args = [
  "-y", "mcp-remote",
  "https://server.stellarix.space/agora-knowledge-mcp/sse",
  "--header", "Authorization: Bearer <USERNAME>:${AGORA_TOKEN}"
]

[mcp_servers."agora-knowledge".env]
AGORA_TOKEN = "<TOKEN>"
PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
```

Replace `<USERNAME>` (e.g. your assigned username) and `<TOKEN>` (your
personal token, issued by the memory owner). Then:

```bash
chmod 600 ~/.codex/config.toml
codex mcp list   # agora-knowledge should show enabled; token shows masked
```

Notes:

- `mcp-remote` needs a recent Node (>= 20.18 recommended). If your default
  node is older, pin an mcp-remote version that supports it, or point
  `command` at a newer node binary with a locally installed mcp-remote.
- Expect exactly two tools (`agora_knowledge_schema`,
  `agora_knowledge_search`) as a read user; a third (`agora_knowledge_save`)
  appears only if you were granted write.
- If your token ever appears in any output, tell the owner immediately so it
  can be rotated.
