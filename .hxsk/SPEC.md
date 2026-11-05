# Collection, MCP and packaging reliability

Preserve previously collected activity across incremental runs and retries. Identify repositories by owner/name. Collect PR/issue updates in update order. An API failure must leave the previous output and successful checkpoints intact and exit nonzero. Skipped stages must retain their own checkpoint and cached totals. Existing Markdown-only exports must be backfilled before using incremental checkpoints.

Support the MCP SDK 1.x API explicitly and keep stdio stdout protocol-only. Built-in analysis templates must work from an installed wheel in any directory. No new runtime libraries are required.

Acceptance: regression checks fail before the fix and pass after it; the complete suite passes on Python 3.12 and 3.13; a clean wheel installation builds an analysis prompt and completes MCP initialize/list/call using a fake gh executable. Also smoke-test deep analysis of the public target repository.
