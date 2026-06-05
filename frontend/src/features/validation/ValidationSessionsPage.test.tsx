import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { I18nProvider } from "../../app/i18n";
import { AppShell } from "../../components/layout/AppShell";
import { createQueryClient } from "../../lib/query";
import { renderWithProviders } from "../../test/test-utils";
import { ValidationSessionsPage } from "./ValidationSessionsPage";

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("渲染 validation_summary.json 中的会话统计和失败用例", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith("/api/v2/validation/sessions")) {
        return jsonResponse({
          records: [
            {
              session_id: "validation-20260605",
              created_at: "2026-06-05T08:00:00+00:00",
              git_commit: "abc1234",
              matrix_path: "docs/superpowers/validation/engineering_validation_matrix.yaml",
              output_dir: "runs/engineering_validation/validation-20260605",
              summary: {
                session_id: "validation-20260605",
                matrix_path: "docs/superpowers/validation/engineering_validation_matrix.yaml",
                total_cases: 2,
                passed_cases: 1,
                failed_cases: 1,
                output_root: "runs/engineering_validation",
                metadata: {},
                results: [
                  {
                    case_id: "case-ok",
                    passed: true,
                    phase: "succeeded",
                    scenario_id: "scenario-ok",
                    output_dir: "cases/case-ok",
                    summary_path: "cases/case-ok/summary.json",
                    failure_reasons: [],
                    observed: { child_run_ids: ["run-ok"] },
                  },
                  {
                    case_id: "case-failed",
                    passed: false,
                    phase: "partial",
                    scenario_id: "scenario-failed",
                    output_dir: "cases/case-failed",
                    summary_path: "cases/case-failed/summary.json",
                    failure_reasons: ["quality gate failed"],
                    observed: { child_run_ids: ["run-failed"] },
                    error: "failed",
                  },
                ],
              },
            },
          ],
        });
      }
      throw new Error(`Unhandled request: GET ${url}`);
    }),
  );

  renderWithProviders(<ValidationSessionsPage />);

  expect(await screen.findByText("validation-20260605")).toBeInTheDocument();
  expect(screen.getAllByText("1 / 2").length).toBeGreaterThan(0);
  expect(screen.getAllByText("50%").length).toBeGreaterThan(0);
  expect(screen.getByText("quality gate failed")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "scenario-failed" })).toHaveAttribute("href", "/scenarios");
  expect(screen.getByRole("link", { name: "run-failed" })).toHaveAttribute("href", "/runs/run-failed");
});

test("空列表和错误状态可读", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(jsonResponse({ records: [] }))
    .mockResolvedValueOnce(jsonResponse({ detail: "broken" }, 500));
  vi.stubGlobal("fetch", fetchMock);

  const { unmount } = renderWithProviders(<ValidationSessionsPage />);
  expect(await screen.findByText("当前还没有已落盘的验证会话。")).toBeInTheDocument();

  unmount();

  renderWithProviders(<ValidationSessionsPage />);
  expect(await screen.findByText("加载验证会话失败。")).toBeInTheDocument();
});

test("缺失 observed 和异常 failure_reasons 时仍能渲染失败用例", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      jsonResponse({
        records: [
          {
            session_id: "validation-defensive",
            created_at: "2026-06-05T08:00:00+00:00",
            git_commit: null,
            matrix_path: "matrix.yaml",
            output_dir: "runs/engineering-validation/validation-defensive",
            summary: {
              session_id: "validation-defensive",
              matrix_path: "matrix.yaml",
              total_cases: 1,
              passed_cases: 0,
              failed_cases: 1,
              output_root: "runs/engineering-validation",
              metadata: {},
              results: [
                {
                  case_id: "case-defensive",
                  passed: false,
                  phase: "failed",
                  scenario_id: null,
                  summary_path: null,
                  failure_reasons: null,
                  error: "fallback error",
                },
              ],
            },
          },
        ],
      }),
    ),
  );

  renderWithProviders(<ValidationSessionsPage />);

  expect(await screen.findByText("case-defensive")).toBeInTheDocument();
  expect(screen.getByText("fallback error")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /run-/i })).not.toBeInTheDocument();
});

test("/validation 路由可达且侧栏导航入口处于 active", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ records: [] })));

  render(
    <I18nProvider>
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
          initialEntries={["/validation"]}
        >
          <Routes>
            <Route path="/" element={<AppShell />}>
              <Route path="validation" element={<ValidationSessionsPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </I18nProvider>,
  );

  expect(await screen.findByRole("heading", { name: "验证会话" })).toBeInTheDocument();
  const navLink = screen.getByRole("link", { name: /验证会话/i });
  expect(navLink).toHaveAttribute("href", "/validation");
  expect(navLink).toHaveAttribute("aria-current", "page");
});
