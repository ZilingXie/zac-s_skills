---
name: agora-knowledge
description: Governed ingestion workflow for shared Agora knowledge in the agora-knowledge AgentMemory MCP. Use when the user asks Codex to remember, save, upload, update, supersede, migrate, review, deduplicate, or draft Agora product, SDK, troubleshooting, SOP, case, document, or architecture knowledge; use when replacing the old Cognee/agora-memory recording workflow; use before calling agora_knowledge_save.
---

# Agora Knowledge

Use this skill as the approval-gated write workflow for shared Agora knowledge.
It replaces the old Cognee `agora-memory` ingestion workflow, but writes to the
`agora-knowledge` AgentMemory MCP.

Before any durable write, read `references/ingestion-workflow.md`.

## Required Boundary

Use only `agora_knowledge_save` for approved durable writes.

Do not use:

```text
raw agentmemory mcp
legacy agoramemory / Cognee MCP
agentmemory-mcp-auth
agentmemory-curated-mcp
```

The public SSE `agora-knowledge` MCP is read-only by default. Users granted
write permission (server-side per-user allowlist) also see
`agora_knowledge_save` over SSE; if that tool is absent for you, writes are
owner-curated — tell the user durable writes require a write grant or the
authenticated server-side stdio entrypoint.

## Write Workflow

For every non-trivial memory request:

1. Confirm the memory belongs in `agora-knowledge`, not `private-info`.
2. Normalize the source into durable Agora knowledge, preferably in English.
3. Choose one canonical project and one valid AgentMemory type.
4. For customer/support/investigation cases, sanitize before search or save.
5. Search for similar memories before drafting.
6. Show up to 5 relevant candidates and explain why they may be related.
7. Draft the proposed `agora_knowledge_save` payload locally.
8. Ask for explicit human approval before saving.
9. Save only after approval.
10. Report the saved memory id and warnings. End successful writes with:

```text
Evolution complete.
```

Clear approval examples include:

```text
approve
upload
save this
add this memory
update existing
可以，保存
批准
```

If the user asks for changes, revise the draft and repeat review.

## Search Before Drafting

Use 2-4 short English search queries based on:

```text
main claim or conclusion
product, SDK, API, platform, or system names
error message, decision, or version constraint
stable unique phrase
```

Search the likely target project first. Search adjacent projects when relevant:

```text
how-to <-> troubleshoot
troubleshoot <-> case
case <-> general
```

Treat results as candidates, not automatic duplicates.

## Guardrails

Ask before saving when:

```text
target profile is unclear
content mixes private owner information with Agora knowledge
customer/support cases are not sanitized
content includes secrets, credentials, tokens, private URLs, account IDs, or private keys
the memory would change or deprecate operational guidance
the source is speculative and status/confidence are unclear
```

Never save raw secrets, raw Authorization headers, unredacted customer details,
sensitive owner personal information, or brainstorming the user has not asked to
remember.

For customer/support cases, remove or generalize customer names, UIDs, SIDs,
RIDs, ticket/CSD IDs, account IDs, private URLs, and private file paths. Use
`sanitization:sanitized` only after these identifiers are removed. If the case
cannot be safely sanitized, ask before saving.

The content header `scope` should normally match the canonical project, such as
`scope:project:cases` for sanitized case memories. Put product or component
names in concepts, tags, facets, or the body instead of inventing a new scope.

## Project Quick Map

```text
how-to         how to use or do something: usage, parameters, procedures, runbooks
troubleshoot   diagnostic knowledge: error meanings, symptom -> cause -> fix paths
case           sanitized support/customer/investigation summaries (what happened)
general        cross-domain knowledge: doc summaries, architecture notes, general facts
```

Routing principle: pick the project by the seeker's scenario (how do I do it /
how do I debug it / what happened), then pick the type by content form.

## Types

```text
fact          one-statement truth: error code meanings, parameter behavior, doc points
bug           incident knowledge with process: symptom, root cause, verified fix
pattern       a rule or best practice seen at least twice
architecture  structure, topology, design decisions
other         fallback
```

## Facets

```text
Required (server rejects the save if missing):
  author, operation, source_kind, sanitization, product

Optional but recommended:
  reference      ticket/doc/PR links or ids
  sdk_version    SDK version the knowledge applies to
```

`product` is a free-form value for now (e.g. rtc, cloud-recording, argus);
values will be consolidated after a run-in period. Search supports
`product` as an exact filter.

Worked example — "error code 1234 means the server is down":

```text
project:   troubleshoot          <- seekers hit this while debugging
type:      fact                  <- a lookup statement, not an incident record
facets:    product=<owning product> + the governance four
concepts:  ["error-1234", "error-code", "server-error"]  <- the code itself MUST be a concept
content:   category:error-code-reference; scope:project:troubleshoot; status:current;
           confidence:0.95; source:doc; date:<today>. Error code 1234 means server-side failure.
```

For Cognee migration history:

```text
agora_shared  -> how-to or troubleshoot
agora_cases   -> case
agora_docs    -> general
agora_archive -> original project with status=deprecated or supersedes_old
```
