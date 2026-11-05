# First portfolio release verification

Verified on 2026-11-05 from baseline 5327470. The earlier suite had 111 tests; the final suite has 151. No existing test was removed or weakened.

## Results

- Python 3.13: `uv run pytest tests/ -q --tb=short` — 151 passed.
- Python 3.12: `uv run --isolated --python 3.12 --extra mcp pytest tests/ -q --tb=short` — 151 passed.
- `uv build` — source distribution and wheel built.
- `scripts/check_wheel.py` on each Python version — 4 base-install checks and 5 MCP-extra checks passed in isolated directories. These execute the installed CLI's manual-project authoring, review, public export, refresh and backup plus MCP initialize/list/call.
- Live public check — repository API -> versioned source -> SQLite workspace -> selected native-ID probe completed against SukbeomH/Acta-Ergo-Sum. Temporary data was removed. No whole-account activity export or paid LLM call was required.
- `git diff --check` — passed.

Initial acceptance checks failed because portfolio modules and the command did not exist. Additional failing-before checks exposed changed-block exclusion, incomplete manifest links, an unavailable editor API, older-input rollback of selected probes, and partial-query reuse of stale public visibility. All were corrected and covered by passing regression checks. Editor integration uses a real test editor subprocess as well as cancellation/conflict tests.

## Acceptance map

| Design case | Executable evidence |
|---|---|
| A01 identities and rename | test_a01_same_names_and_rename_keep_selection; test_repository_rename_keeps_identity_and_old_aliases |
| A02 retained cache | test_a02_retained_cache_is_not_a_new_observation; test_native_ids_and_actual_observations_survive_cached_rows |
| A03 meaningful changes | test_a03_observation_time_and_display_changes_do_not_invalidate |
| A04 scoped/idempotent impacts | test_a04_changed_evidence_invalidates_only_dependents_idempotently; test_excluded_changed_block_does_not_block_other_confirmed_claim |
| A05 inaccessible and failed probes | test_a05_probe_failure_preserves_human_content; tests/test_portfolio_probe.py |
| A06 edited revisions | test_a06_edits_preserve_versions_and_require_review; test_stale_editor_preserves_its_proposal |
| A07 qualitative/quantitative claims | test_a07_qualitative_allowed_missing_measurement_blocked |
| A08 public disclosure | test_a08_private_dependencies_block_document_and_manifest; test_partial_pr_query_cannot_reuse_stale_public_visibility; test_older_body_observation_cannot_revert_newer_privacy_check |
| A09 two sessions | test_a09_stale_editor_conflicts_without_lost_updates; test_real_two_session_revision_conflict |
| A10 failure/schema | test_a10_atomic_failure_and_future_schema; test_invalid_source_does_not_create_workspace |
| A11 publication race | test_a11_prepared_export_rechecks_disclosure; test_publication_race_does_not_leave_partial_bundle |
| A12 complete lifecycle | test_public_private_manual_projects_complete_refresh_cycle; test_installed_portfolio_manual_round_trip |
| A13 source consistency | test_a13_snapshot_integrity_and_one_descriptor; test_one_open_descriptor_cannot_mix_replaced_input; test_same_snapshot_id_with_resealed_changes_is_rejected |
| A14 compatibility/no model | full existing suite, test_a14_cli_available_without_external_model, installed base/MCP checks |

The first store implementation keeps the domain aggregate and immutable histories in one SQLite JSON row. Transactions and expected revisions serialize writes; domain methods validate references. Public Markdown and its evidence manifest are derived together and rechecked before publication under a read transaction. Confirmation records user judgment, not independent proof of factual or semantic correctness.
