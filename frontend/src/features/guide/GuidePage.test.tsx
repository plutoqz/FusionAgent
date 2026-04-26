import { screen } from "@testing-library/react";

import { renderWithProviders } from "../../test/test-utils";
import { GuidePage } from "./GuidePage";

test("默认渲染中文教程页与关键操作入口", () => {
  renderWithProviders(<GuidePage />, { path: "/guide", route: "/guide" });

  expect(screen.getByRole("heading", { name: /使用指南/i })).toBeInTheDocument();
  expect(screen.getByText(/开场检查/i)).toBeInTheDocument();
  expect(screen.getByText(/执行一条任务/i)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /1\. 模型设置/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /前往模型设置/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /打开新建任务/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /查看场景与报告/i })).toBeInTheDocument();
});
