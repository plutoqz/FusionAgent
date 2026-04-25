import { screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { renderWithProviders } from "../../test/test-utils";
import { RunDetailPage } from "./RunDetailPage";

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

test("默认使用中文展示工作流、预览和审计面板", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url.includes("/inspection")) {
        return new Response(
          JSON.stringify({
            run: {
              run_id: "run-demo",
              job_type: "building",
              trigger: { type: "user_query", content: "Inspect flood extent" },
              phase: "running",
              progress: 48,
              created_at: "2026-04-25T10:00:00Z",
            },
            plan: {
              workflow_id: "wf-001",
              expected_output: "vector",
              estimated_time: "unknown",
              tasks: [
                {
                  step: 1,
                  name: "Collect source data",
                  description: "fetch and stage bundles",
                  algorithm_id: "algo.fetch",
                  depends_on: [],
                },
              ],
            },
            audit_events: [
              {
                timestamp: "2026-04-25T10:01:00Z",
                kind: "planning",
                message: "workflow assembled",
                progress: 20,
              },
            ],
            artifact: {
              available: false,
            },
            kg_path_trace: {},
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      return new Response(
        JSON.stringify({
          run_id: "run-demo",
          geojson_path: "/api/v2/runs/run-demo/preview.geojson",
          bbox: null,
          preview_feature_count: 0,
          feature_count: 0,
          layers: [],
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    }),
  );

  renderWithProviders(<RunDetailPage />, {
    path: "/runs/:runId",
    route: "/runs/run-demo",
  });

  expect(await screen.findByText(/工作流计划/i)).toBeInTheDocument();
  expect(screen.getByText(/结果预览/i)).toBeInTheDocument();
  expect(screen.getByText(/审计时间线/i)).toBeInTheDocument();
});
