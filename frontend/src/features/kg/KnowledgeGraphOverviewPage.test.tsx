import { screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { renderWithProviders } from "../../test/test-utils";
import { KnowledgeGraphOverviewPage } from "./KnowledgeGraphOverviewPage";

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

test("默认渲染知识图谱总览图例", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(
        JSON.stringify({
          nodes: [
            { id: "wp.flood.building.default", kind: "workflow_pattern", label: "Flood Building Default", meta: {} },
            { id: "algo.fusion.building.v1", kind: "algorithm", label: "Building Fusion", meta: {} },
            { id: "catalog.flood.building", kind: "data_source", label: "Flood Building Bundle", meta: {} },
          ],
          edges: [
            {
              source: "wp.flood.building.default",
              target: "algo.fusion.building.v1",
              relationship: "uses_algorithm",
              meta: {},
            },
          ],
          meta: {
            graph_type: "overview",
            pattern_count: 1,
            algorithm_count: 1,
            data_source_count: 1,
            edge_count: 1,
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    ),
  );

  renderWithProviders(<KnowledgeGraphOverviewPage />);

  expect(await screen.findByText(/工作流模式/i)).toBeInTheDocument();
  expect(screen.getByText(/算法/i)).toBeInTheDocument();
  expect(screen.getByText(/数据源/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /缩小图谱/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /适配视图/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /放大图谱/i })).toBeInTheDocument();
  expect(screen.getByText(/拖动画布查看上下游关系/i)).toBeInTheDocument();
});
