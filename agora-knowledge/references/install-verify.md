# Verify your connection

With your credential (`username:token`):

```bash
# 1. Auth check — expect HTTP 200 (the stream opens):
curl -s -o /dev/null -w '%{http_code}\n' --max-time 3 \
  -H "Authorization: Bearer <USERNAME>:<TOKEN>" \
  https://server.stellarix.space/agora-knowledge-mcp/sse

# 2. No credential — expect HTTP 401:
curl -s -o /dev/null -w '%{http_code}\n' --max-time 3 \
  https://server.stellarix.space/agora-knowledge-mcp/sse

# 3. From your agent: tools/list should show
#    agora_knowledge_schema + agora_knowledge_search (read users)
#    (+ agora_knowledge_save for write-granted users)
# 4. Smoke search (project must be one of the canonical namespaces):
#    agora_knowledge_search(query="cloud recording", project="troubleshooting")
```

If step 1 returns 401, your token is wrong or was rotated — ask the owner.
If it returns 200 but your agent sees no tools, check the client MCP logs
and the mcp-remote bridge Node version.
