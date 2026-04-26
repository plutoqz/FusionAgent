import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { App } from "./App";

afterEach(() => {
  window.localStorage.clear();
});

test("默认以中文渲染导航壳子", () => {
  render(<App />);
  expect(screen.getByRole("complementary", { name: /主导航/i })).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: /知识图谱/i }).length).toBeGreaterThan(0);
  expect(screen.getAllByRole("link", { name: /模型设置/i }).length).toBeGreaterThan(0);
  expect(screen.getAllByRole("link", { name: /使用指南/i }).length).toBeGreaterThan(0);
});

test("允许切换到英文界面", () => {
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: /english/i }));
  expect(screen.getAllByRole("link", { name: /knowledge graph/i }).length).toBeGreaterThan(0);
  expect(screen.getAllByRole("link", { name: /llm settings/i }).length).toBeGreaterThan(0);
  expect(screen.getAllByRole("link", { name: /guide/i }).length).toBeGreaterThan(0);
});
