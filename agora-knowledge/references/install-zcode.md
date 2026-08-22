# ZCode MCP setup

Add to `~/.zcode/cli/config.json` (user scope, `mcp.servers`). ZCode speaks
stdio MCP, so use the `mcp-remote` bridge for the SSE endpoint. Requires
Node >= 18 on PATH.

```json
{
  "mcp": {
    "servers": {
      "agora-knowledge": {
        "command": "npx",
        "args": [
          "-y", "mcp-remote",
          "https://server.stellarix.space/agora-knowledge-mcp/sse",
          "--header", "Authorization: Bearer <USERNAME>:<TOKEN>"
        ]
      }
    }
  }
}
```

Replace `<USERNAME>` and `<TOKEN>` with your assigned username and personal
token (issued by the memory owner). Keep the file readable only by you:

```bash
chmod 600 ~/.zcode/cli/config.json
```

Verify in ZCode: **Settings → MCP** should show `agora-knowledge` connected,
with exactly `agora_knowledge_schema` + `agora_knowledge_search`
(read users), plus `agora_knowledge_save` if you were granted write.

To install the companion skill for ZCode:

```bash
mkdir -p ~/.zcode/skills
cp -r skills/agora-knowledge ~/.zcode/skills/
```
