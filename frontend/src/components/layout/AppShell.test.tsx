import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { I18nProvider } from "../../app/i18n";
import { AppShell } from "./AppShell";

function renderAppShell(route: string) {
  return render(
    <I18nProvider>
      <MemoryRouter
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        initialEntries={[route]}
      >
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route index element={<div>home</div>} />
            <Route path="runs/new" element={<div>new run</div>} />
            <Route path="runs" element={<div>runs list</div>} />
            <Route path="runs/:runId" element={<div>run detail</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </I18nProvider>,
  );
}

test("进入新建任务页时不会同时点亮历史任务", () => {
  renderAppShell("/runs/new");

  const newRunLink = screen.getByRole("link", { name: /新建任务/i });
  const historyLink = screen.getByRole("link", { name: /历史任务/i });

  expect(newRunLink).toHaveClass("active");
  expect(newRunLink).toHaveAttribute("aria-current", "page");
  expect(historyLink).not.toHaveClass("active");
  expect(historyLink).not.toHaveAttribute("aria-current");
});

test("进入历史任务详情页时保持高亮历史任务", () => {
  renderAppShell("/runs/run-123");

  const newRunLink = screen.getByRole("link", { name: /新建任务/i });
  const historyLink = screen.getByRole("link", { name: /历史任务/i });

  expect(newRunLink).not.toHaveClass("active");
  expect(newRunLink).not.toHaveAttribute("aria-current");
  expect(historyLink).toHaveClass("active");
  expect(historyLink).toHaveAttribute("aria-current", "page");
});
