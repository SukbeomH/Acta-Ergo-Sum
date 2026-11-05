# Implementation plan

1. Reproduce data loss, owner collisions, update-order cutoff, failed-run checkpoint advancement, MCP startup, and missing installed templates in regression tests.
2. Keep normalized activity records alongside Markdown, merge by stable identity, and render cumulative totals. Backfill legacy outputs. Stage collection in a sibling directory; replace output only after all enabled stages succeed. Record run-start checkpoints per stage.
3. Raise explicit API errors; tolerate only expected optional 404s. Preserve owner/name through queries and filenames. Align PR/issue update ordering and cutoffs.
4. Constrain the existing MCP dependency to the supported major, fix initialization, send logs to stderr, and exercise the real stdio protocol. Include existing templates in wheels and resolve them as package resources.
5. Run focused and full checks, wheel smoke tests, inspect the diff, then make one commit and push the current branch.
