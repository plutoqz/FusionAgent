from pathlib import Path


def test_runtime_claims_do_not_exceed_locked_boundary() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    readme_en = Path("README.en.md").read_text(encoding="utf-8")
    ops = Path("docs/v2-operations.md").read_text(encoding="utf-8")
    no_ui_ops = Path("docs/no-ui-agent-operations.md").read_text(encoding="utf-8")

    assert "trajectory-to-road remains reservation-only" in ops
    assert "registered tool contracts" in ops
    assert "unsupported-intent rejection" in ops
    assert "checkpoint recovery redispatch" in ops
    assert "研究原型" in readme
    assert "不应表述为生产级平台" in readme
    assert "research prototype" in readme_en
    assert "do not establish production readiness" in readme_en
    assert "large-AOI `OSM + single-reference` building runtime" in ops
    assert "trajectory-to-road remains reservation-only" in no_ui_ops
    assert "not a live runtime ingestion path" in no_ui_ops

