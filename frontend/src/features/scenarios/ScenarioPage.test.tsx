import { screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { renderWithProviders } from "../../test/test-utils";
import { ScenarioPage } from "./ScenarioPage";

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

test("默认渲染场景表单以及中英文报告标签", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

      if (url.endsWith("/api/v2/scenario-runs")) {
        return new Response(
          JSON.stringify({
            records: [
              {
                scenario_id: "scenario-001",
                scenario_name: "沿海洪涝演练",
                phase: "succeeded",
              },
            ],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      if (url.endsWith("/api/v2/scenario-runs/scenario-001/documents")) {
        return new Response(
          JSON.stringify({
            scenario_id: "scenario-001",
            documents: [
              {
                filename: "scenario_report.zh.md",
                path: "scenario_report.zh.md",
                size_bytes: 128,
                language: "zh",
              },
              {
                filename: "scenario_report.en.md",
                path: "scenario_report.en.md",
                size_bytes: 128,
                language: "en",
              },
            ],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      return new Response(
        JSON.stringify({
          scenario_id: "scenario-001",
          filename: url.includes(".zh.") ? "scenario_report.zh.md" : "scenario_report.en.md",
          path: "report.md",
          content: url.includes(".zh.") ? "# 中文报告" : "# English Report",
          size_bytes: 128,
          language: url.includes(".zh.") ? "zh" : "en",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    }),
  );

  renderWithProviders(<ScenarioPage />);

  expect(await screen.findByLabelText(/场景名称/i)).toBeInTheDocument();
  expect(await screen.findByRole("tab", { name: /中文报告/i })).toBeInTheDocument();
  expect(await screen.findByRole("tab", { name: /english report/i })).toBeInTheDocument();
});
