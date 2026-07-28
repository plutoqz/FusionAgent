# Branch Documentation Audit - 2026-07-10

Supersession note, 2026-07-10:

This audit records the first cleanup pass. It has been superseded by
`docs/CURRENT.md` for active project navigation. In particular, the earlier
"Documents Kept In Place" section should not be read as granting current
authority to old operations, scenario harness, maturity freeze, or evidence
freeze documents. They remain available as historical material unless a current
entry point explicitly reactivates them.

## Current Local State

Current checked-out branch: `main`.

Known local/remote refs at audit time:

- `main`
- `codex/evidence-and-road-followups`
- `origin/main`
- `origin/codex/evidence-and-road-followups`

Remote refresh was attempted with `git fetch --all --prune`, but GitHub HTTPS reset the connection:

```text
fatal: unable to access 'https://github.com/plutoqz/FusionAgent.git/': OpenSSL SSL_read: Connection was reset, errno 10054
```

So this audit is based on local refs and existing remote-tracking refs.

## Documents Archived In This Cleanup

Moved to `docs/pasted/conversation-handoffs/`:

- `文档/handoff_ClaudeCode_2026-07-07.md`
- `文档/handoff_ClaudeCode_2026-07-07.summary_version.bak.md`

Moved to `docs/pasted/legacy-research-notes/`:

- `文档/研究总结0529.md`

Moved to `docs/pasted/legacy-thesis/`:

- `docs/thesis/experiment-results-draft.md`

## Documents Kept In Place

Kept as current or potentially active:

- `docs/thesis/research_direction_guide_2026-07-09.md`
- `docs/loop-testing-prompt.md`
- `docs/v2-operations.md`
- `docs/no-ui-agent-operations.md`
- `docs/local-direct-run.md`

Reason: these may still guide the new research/application split or the engineering robustness loop.

Existing historical folders such as `docs/superpowers/plans/done/`, `docs/superpowers/plans/discard/`, and `docs/superpowers/specs/done/` were not moved. They are already archived semantically, and moving them now would create large churn without improving the current split.

## Other Branch Documentation Differences

Local branch `codex/evidence-and-road-followups` contains additional thesis/evidence documents not currently on `main`, including:

- `docs/thesis/README.md`
- `docs/thesis/chapters/chapter-01-research-background-draft.md`
- `docs/thesis/chapters/chapter-02-related-work-draft.md`
- `docs/thesis/chapters/chapter-03-technical-route-draft.md`
- `docs/thesis/chapters/chapter-04-experiment-design-draft.md`
- `docs/thesis/chapters/chapter-05-results-analysis-draft.md`
- `docs/thesis/evidence/evidence-index.md`
- `docs/thesis/experiments/experiment-roadmap.md`
- `docs/thesis/experiments/next-execution-list.md`
- several `docs/superpowers/specs/*manifest.json` files dated 2026-06-10 to 2026-06-26.

These should not be merged blindly. Before merging, compare them against the current research direction:

- keep material that supports product-contract KG, quality gates, evidence, and experiment cases;
- archive material that assumes the older "agent runtime governance / evidence freeze" thesis framing;
- avoid reviving old claims about generic KG+LLM Agent novelty.

## Next Cleanup Step

After network access succeeds:

1. Run `git fetch --all --prune`.
2. Re-run branch diff for docs:

   ```powershell
   git diff --name-status main..origin/codex/evidence-and-road-followups -- docs "文档"
   ```

3. Decide whether to cherry-pick useful thesis drafts into the current `docs/thesis/` direction or archive them under `docs/pasted/legacy-thesis/`.

