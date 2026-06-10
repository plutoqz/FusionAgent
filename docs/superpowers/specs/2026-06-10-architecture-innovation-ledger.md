# Architecture Innovation Ledger

| innovation_id | reviewer_objection | current_gap | MVP_behavior | metric | evidence_file | claim_boundary | future_work |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AI-1 | KG is only prompt context | Validator and planner could report issues without hard rejection | Runtime contract rejects blocked algorithms and records fallback | validator_rejection_rate, kg_fallback_rate | Freeze A and A2b evidence | KG constrains runtime; it does not make LLM planning optimal | richer graph constraints |
| AI-2 | Healing is hardcoded engineering | Executor order was embedded in code | Repair decisions include policy_source, candidate_actions, selected_action, skipped_actions | policy_sourced_repair_count, healing_success_rate | repair audit records | Policy governs existing repair capabilities | learned repair cost model |
| AI-3 | Durable Learning is decorative | Summary key was too coarse for decision evidence | Conditioned summaries enter candidate evidence | conditioned_summary_count, nonzero_adjustment_count | architecture MVP evidence | Bounded policy hints only | causal learning and online policy tuning |
