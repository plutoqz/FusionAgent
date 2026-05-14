from pathlib import Path


def test_runtime_claims_do_not_exceed_locked_boundary() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    readme_en = Path("README.en.md").read_text(encoding="utf-8")
    ops = Path("docs/v2-operations.md").read_text(encoding="utf-8")
    no_ui_ops = Path("docs/no-ui-agent-operations.md").read_text(encoding="utf-8")

    assert "trajectory-to-road remains reservation-only" in ops
    assert "registered tool contracts" in readme
    assert "unsupported-intent rejection" in readme
    assert "checkpoint recovery inspection" in readme
    assert "FusionAgent 当前可以作为无界面的成熟矢量数据融合智能体运行" in readme
    assert "FusionAgent can now run as a mature no-UI vector data fusion agent" in readme_en
    assert "large-AOI `OSM + single-reference` building runtime" in ops
    assert "trajectory-to-road remains reservation-only" in no_ui_ops
    assert "not a live runtime ingestion path" in no_ui_ops

