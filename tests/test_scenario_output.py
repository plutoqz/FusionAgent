from services.scenario_output import DEFAULT_SCENARIO_OUTPUT_ROOT, resolve_scenario_output_root


def test_resolve_scenario_output_root_uses_request_value(monkeypatch, tmp_path):
    monkeypatch.delenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", raising=False)

    resolved = resolve_scenario_output_root(str(tmp_path / "custom"))

    assert resolved == tmp_path / "custom"


def test_resolve_scenario_output_root_uses_environment_when_request_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", str(tmp_path / "configured"))

    resolved = resolve_scenario_output_root(None)

    assert resolved == tmp_path / "configured"


def test_resolve_scenario_output_root_uses_project_default_when_unconfigured(monkeypatch):
    monkeypatch.delenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", raising=False)
    monkeypatch.delenv("GEOFUSION_OUTPUT_ROOT", raising=False)

    resolved = resolve_scenario_output_root(None)

    assert resolved == DEFAULT_SCENARIO_OUTPUT_ROOT
    assert str(resolved) == r"D:\fyx\data\fusionagent_scenarios"
