import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { renderWithProviders } from "../../test/test-utils";
import { ScenarioPage } from "./ScenarioPage";

type ScenarioRecord = {
  scenario_id: string;
  scenario_name?: string;
  phase: string;
  child_run_ids?: string[];
  checkpoint?: {
    recoverable?: boolean | null;
    stale?: boolean | null;
    failed_child_run_ids?: string[] | null;
    failed_children?: string[] | null;
  } | null;
  checkpoint_metadata?: {
    recoverable?: boolean | null;
    stale?: boolean | null;
    failed_child_run_ids?: string[] | null;
    failed_children?: string[] | null;
  } | null;
};

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function stubScenarioPageFetch({
  initialRecords,
  refreshedRecords = initialRecords,
  resumeScenarioId = initialRecords[0]?.scenario_id ?? "scenario-001",
  resumeResponse,
}: {
  initialRecords: ScenarioRecord[];
  refreshedRecords?: ScenarioRecord[];
  resumeScenarioId?: string;
  resumeResponse?: Response | (() => Response | Promise<Response>);
}) {
  let scenarioListCalls = 0;
  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

    if (url.endsWith("/api/v2/scenario-runs")) {
      scenarioListCalls += 1;
      return jsonResponse({
        records: scenarioListCalls > 1 ? refreshedRecords : initialRecords,
      });
    }

    if (url.includes("/api/v2/scenario-runs/") && url.includes("/resume")) {
      if (resumeResponse) {
        return typeof resumeResponse === "function" ? resumeResponse() : resumeResponse;
      }
      return jsonResponse({
        scenario_id: resumeScenarioId,
        phase: "running",
        output_dir: "outputs/scenarios/resumed",
        child_run_ids: ["run-resumed"],
      });
    }

    if (url.includes("/documents/")) {
      const scenarioId = url.match(/scenario-runs\/([^/]+)\/documents/)?.[1] ?? "scenario-001";
      return jsonResponse({
        scenario_id: scenarioId,
        filename: "scenario_report.zh.md",
        path: "scenario_report.zh.md",
        content: "# 中文报告",
        size_bytes: 128,
        language: "zh",
      });
    }

    if (url.includes("/api/v2/scenario-runs/") && url.endsWith("/documents")) {
      const scenarioId = url.match(/scenario-runs\/([^/]+)\/documents/)?.[1] ?? "scenario-001";
      return jsonResponse({
        scenario_id: scenarioId,
        documents: [
          {
            filename: "scenario_report.zh.md",
            path: "scenario_report.zh.md",
            size_bytes: 128,
            language: "zh",
          },
        ],
      });
    }

    throw new Error(`Unhandled request: ${init?.method ?? "GET"} ${url}`);
  });

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

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

      if (url.endsWith("/api/v2/scenario-runs/scenario-001/documents/scenario_report.zh.md")) {
        return jsonResponse({
          scenario_id: "scenario-001",
          filename: "scenario_report.zh.md",
          path: "report.md",
          content: "# 中文报告",
          size_bytes: 128,
          language: "zh",
        });
      }

      if (url.endsWith("/api/v2/scenario-runs/scenario-001/documents/scenario_report.en.md")) {
        return jsonResponse({
          scenario_id: "scenario-001",
          filename: "scenario_report.en.md",
          path: "report.md",
          content: "# English Report",
          size_bytes: 128,
          language: "en",
        });
      }

      throw new Error(`Unhandled request: GET ${url}`);
    }),
  );

  renderWithProviders(<ScenarioPage />);

  expect(await screen.findByLabelText(/场景名称/i)).toBeInTheDocument();
  expect(await screen.findByRole("tab", { name: /中文报告/i })).toBeInTheDocument();
  expect(await screen.findByRole("tab", { name: /english report/i })).toBeInTheDocument();
});

test("running 和 partial 场景显示恢复操作", async () => {
  stubScenarioPageFetch({
    initialRecords: [
      {
        scenario_id: "scenario-running",
        scenario_name: "运行中场景",
        phase: "running",
        child_run_ids: ["run-1"],
      },
      {
        scenario_id: "scenario-partial",
        scenario_name: "部分完成场景",
        phase: "partial",
        child_run_ids: ["run-2"],
      },
    ],
  });

  renderWithProviders(<ScenarioPage />);

  expect(await screen.findByRole("button", { name: /恢复场景/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /重试失败任务/i })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /部分完成场景/i }));

  expect(await screen.findByRole("button", { name: /恢复场景/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /重试失败任务/i })).toBeInTheDocument();
});

test("点击普通恢复会 POST resume 并刷新后保持返回的场景选中", async () => {
  const fetchMock = stubScenarioPageFetch({
    initialRecords: [
      {
        scenario_id: "scenario-running",
        scenario_name: "运行中场景",
        phase: "running",
        child_run_ids: ["run-1"],
      },
    ],
    refreshedRecords: [
      {
        scenario_id: "scenario-running",
        scenario_name: "已恢复场景",
        phase: "running",
        child_run_ids: ["run-resumed"],
      },
    ],
    resumeScenarioId: "scenario-running",
  });

  renderWithProviders(<ScenarioPage />);

  fireEvent.click(await screen.findByRole("button", { name: /恢复场景/i }));

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v2/scenario-runs/scenario-running/resume",
      expect.objectContaining({ method: "POST" }),
    );
  });
  expect(await screen.findAllByText("已恢复场景")).toHaveLength(2);
  expect(screen.getByText("run-resumed")).toBeInTheDocument();
});

test("点击重试失败任务会携带 retry_failed=true", async () => {
  const fetchMock = stubScenarioPageFetch({
    initialRecords: [
      {
        scenario_id: "scenario-partial",
        scenario_name: "部分完成场景",
        phase: "partial",
        child_run_ids: ["run-1", "run-2"],
      },
    ],
  });

  renderWithProviders(<ScenarioPage />);

  fireEvent.click(await screen.findByRole("button", { name: /重试失败任务/i }));

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v2/scenario-runs/scenario-partial/resume?retry_failed=true",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

test("succeeded 场景不显示恢复操作", async () => {
  stubScenarioPageFetch({
    initialRecords: [
      {
        scenario_id: "scenario-succeeded",
        scenario_name: "成功场景",
        phase: "succeeded",
        child_run_ids: ["run-1"],
      },
    ],
  });

  renderWithProviders(<ScenarioPage />);

  expect(await screen.findByText("成功场景")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /恢复场景/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /重试失败任务/i })).not.toBeInTheDocument();
});

test("partial 场景存在明确不可恢复 metadata 时不显示恢复操作", async () => {
  stubScenarioPageFetch({
    initialRecords: [
      {
        scenario_id: "scenario-degraded",
        scenario_name: "降级完成场景",
        phase: "partial",
        child_run_ids: ["run-1"],
        checkpoint_metadata: {
          recoverable: false,
          stale: false,
          failed_child_run_ids: [],
          failed_children: [],
        },
      },
    ],
  });

  renderWithProviders(<ScenarioPage />);

  expect(await screen.findByText("降级完成场景")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /恢复场景/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /重试失败任务/i })).not.toBeInTheDocument();
});

test("partial 场景有失败子任务或 recoverable metadata 时显示恢复操作", async () => {
  stubScenarioPageFetch({
    initialRecords: [
      {
        scenario_id: "scenario-failed-children",
        scenario_name: "失败子任务场景",
        phase: "partial",
        child_run_ids: ["run-1"],
        checkpoint_metadata: {
          recoverable: false,
          failed_child_run_ids: ["run-1"],
        },
      },
      {
        scenario_id: "scenario-recoverable",
        scenario_name: "元数据允许场景",
        phase: "partial",
        child_run_ids: ["run-2"],
        checkpoint_metadata: {
          recoverable: true,
        },
      },
    ],
  });

  renderWithProviders(<ScenarioPage />);

  expect(await screen.findByRole("button", { name: /恢复场景/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /重试失败任务/i })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /元数据允许场景/i }));

  expect(await screen.findByRole("button", { name: /恢复场景/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /重试失败任务/i })).toBeInTheDocument();
});

test("pending 时只在被点击的恢复按钮显示提交中", async () => {
  let resolveResume: (response: Response) => void = () => {};
  stubScenarioPageFetch({
    initialRecords: [
      {
        scenario_id: "scenario-running",
        scenario_name: "运行中场景",
        phase: "running",
        child_run_ids: ["run-1"],
      },
    ],
    resumeResponse: () =>
      new Promise<Response>((resolve) => {
        resolveResume = resolve;
      }),
  });

  renderWithProviders(<ScenarioPage />);

  fireEvent.click(await screen.findByRole("button", { name: /恢复场景/i }));

  expect(await screen.findByRole("button", { name: /提交中/i })).toBeDisabled();
  expect(screen.getByRole("button", { name: /重试失败任务/i })).toBeDisabled();

  resolveResume(
    jsonResponse({
      scenario_id: "scenario-running",
      phase: "running",
      output_dir: "outputs/scenarios/resumed",
      child_run_ids: ["run-resumed"],
    }),
  );
});

test("恢复错误消息为空时显示 fallback 文案", async () => {
  stubScenarioPageFetch({
    initialRecords: [
      {
        scenario_id: "scenario-running",
        scenario_name: "运行中场景",
        phase: "running",
        child_run_ids: ["run-1"],
      },
    ],
    resumeResponse: new Response(JSON.stringify({ detail: "   " }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    }),
  });

  renderWithProviders(<ScenarioPage />);

  fireEvent.click(await screen.findByRole("button", { name: /恢复场景/i }));

  expect(await screen.findByText("恢复场景失败。")).toBeInTheDocument();
});
