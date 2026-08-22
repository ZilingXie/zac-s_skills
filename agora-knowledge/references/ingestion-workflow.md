# Agora-Knowledge Ingestion Reference

Use this reference before calling `agora_knowledge_save`.

## Canonical Projects

```text
product
sdk
troubleshooting
cases
sop
docs
architecture
other
```

Use `other` only as a temporary holding area.

## Cognee Mapping

Cognee used datasets. AgentMemory uses projects.

```text
agora_shared:
  Choose product, sdk, troubleshooting, or sop by future recall purpose.

agora_cases:
  Use cases.

agora_docs:
  Use docs by default.
  Use architecture for topology/design.
  Use sdk for API/SDK docs.

agora_archive:
  Keep the original project.
  Use status=deprecated or status=supersedes_old.
```

Cognee frontmatter fields map to AgentMemory fields/facets:

```text
memory_id:
  Native saved memory id after write.
  For migration, store old Cognee id as facet legacy_memory_id.

author:
  facet author:<username>.

created_at:
  content header date, or facet created_at:<YYYY-MM-DD> for imports.

type=fact:
  type=fact.

type=procedure:
  type=workflow.

type=doc:
  type=fact, architecture, or workflow depending on content.

type=case:
  project=cases.
  type=fact by default.
  type=bug for defect behavior.

dataset:
  project.
  For migration, add facet legacy_dataset:<dataset>.

operation:
  facet operation:remember|update|deprecate|migration.

status=current:
  content header status=current.

status=archived:
  content header status=deprecated.

source_hash/content_hash:
  facets source_hash:<sha256> and content_hash:<sha256> when available.

supersedes_memory_id/update_of_memory_id:
  facets with the same dimensions when known.
```

## Required Save Shape

Use:

```text
type      fact | preference | workflow | architecture | bug | pattern
project   one canonical agora-knowledge project
concepts  3-8 stable lookup keys, not full sentences
content   required header plus concise durable statement
files     relevant paths when applicable
tags      optional flat labels
facets    exact dimension/value labels for metadata
graph     true only for high-value entity relationships
```

Content must start with:

```text
category:<short_category>; scope:<global|project:NAME|ops|coding>; status:<current|supersedes_old|deprecated|tentative|needs_review>; confidence:<0.0-1.0>; source:<codex|manual|hermes|claude|ops>; date:<YYYY-MM-DD>. <statement>
```

For `agora-knowledge`, normally use `scope:project:<project>`. For example,
sanitized case memories should use `scope:project:cases`; put product,
component, or feature names in concepts, tags, facets, or the body rather than
creating ad hoc scopes.

## Customer Case Sanitization

Before saving support, customer, or investigation cases, remove or generalize:

```text
customer names
UIDs, SIDs, RIDs, CIDs, account IDs, app IDs, project IDs
ticket, CSD, Zendesk, Salesforce, or internal case numbers
private URLs and hostnames
private file paths or thread paths
email addresses, phone numbers, names, or direct contacts
raw log lines that contain identifiers or secrets
```

Keep reusable technical facts:

```text
product or component area
symptom
source media or platform characteristics when non-identifying
root cause
short-term mitigation
long-term fix
validation method
version or parameter constraints when relevant
```

Use:

```text
source_kind:case
sanitization:sanitized
project:cases
scope:project:cases
```

If sanitization would remove the core meaning or if identifiers are necessary
for follow-up, ask the user before saving.

## Required And Recommended Facets

The server requires these facets for `agora_knowledge_save`:

```text
author:<username>
operation:remember|update|deprecate|migration
source_kind:manual|chat|doc|case|migration|code
sanitization:sanitized|not_applicable
```

Use additional facets for exact metadata when available:

```text
source_hash:<sha256>
content_hash:<sha256>
legacy_system:cognee
legacy_dataset:agora_shared|agora_cases|agora_docs|agora_archive
legacy_memory_id:<old-id>
supersedes_memory_id:<memory-id>
update_of_memory_id:<memory-id>
```

Do not store raw secrets, private URLs, customer identifiers, or raw
Authorization headers in facets.

## Similarity Search

Before drafting, search with 2-4 short English queries:

```text
main claim or conclusion
product, SDK, API, platform, or system names
error message, decision, or version constraint
stable unique phrase
```

Search the likely project first. Search adjacent projects when relevant:

```text
product <-> sdk
troubleshooting <-> cases
sop <-> troubleshooting
docs <-> architecture
docs <-> sdk
```

Show up to 5 candidates with:

```text
project
memory id
summary
why it may be related
```

Candidate decisions:

```text
No close candidate:
  Add a new memory with status=current.

Same fact already exists and is current:
  Do not save. Report the existing memory id if useful.

Same topic but new detail:
  Add a new memory if independently useful.
  Use update/supersede if it changes prior guidance.

Old guidance is wrong or outdated:
  Save a new memory with status=supersedes_old.
  Add supersedes/update facets when old id is known.

Useful but uncertain:
  Use status=tentative or needs_review.
  Use confidence below 0.8.

Private or insufficiently sanitized:
  Do not save to agora-knowledge.
```

## Update And Archive Model

Do not recreate Cognee's `agora_archive` as a project.

For outdated knowledge:

```text
Save the corrected memory in the original project.
Set status=supersedes_old when replacing previous guidance.
Set status=deprecated for historical obsolete references.
Add supersedes_memory_id/update_of_memory_id facets when known.
State old and new guidance in content when useful.
```

Avoid silent overwrite behavior.

## Audit

The wrapper audit log is:

```text
the server-side audit log (maintained by the MCP operator)
```

Audit may include project/type/status/source/counts/hashes/memory id/success.
Audit must not include memory body, raw search query, token values, raw
Authorization headers, or raw secret values.

## Example Payload

```json
{
  "type": "workflow",
  "project": "sop",
  "concepts": [
    "token rotation",
    "public mcp",
    "agora knowledge",
    "read only access"
  ],
  "content": "category:access_control; scope:project:sop; status:current; confidence:0.95; source:manual; date:2026-07-09. Public agora-knowledge MCP users should be added or rotated with the server-side helper, and public clients should receive only the read-only SSE endpoint plus a username:token bearer credential.",
  "tags": ["mcp", "auth", "public-access"],
  "facets": [
    {"dimension": "author", "value": "owner"},
    {"dimension": "operation", "value": "remember"},
    {"dimension": "source_kind", "value": "manual"},
    {"dimension": "sanitization", "value": "not_applicable"}
  ],
  "graph": false
}
```
