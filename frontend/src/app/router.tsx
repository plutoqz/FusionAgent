import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { GuidePage } from "../features/guide/GuidePage";
import { HomePage } from "../features/home/HomePage";
import { KnowledgeGraphOverviewPage } from "../features/kg/KnowledgeGraphOverviewPage";
import { RunPathGraphPage } from "../features/kg/RunPathGraphPage";
import { RunComparePage } from "../features/runs/RunComparePage";
import { RunCreatePage } from "../features/runs/RunCreatePage";
import { RunDetailPage } from "../features/runs/RunDetailPage";
import { RunsPage } from "../features/runs/RunsPage";
import { ScenarioPage } from "../features/scenarios/ScenarioPage";
import { LlmSettingsPage } from "../features/settings/LlmSettingsPage";
import { ValidationSessionsPage } from "../features/validation/ValidationSessionsPage";

export const router = createBrowserRouter(
  [
    {
      path: "/",
      element: <AppShell />,
      children: [
        {
          index: true,
          element: <HomePage />,
        },
        {
          path: "runs/new",
          element: <RunCreatePage />,
        },
        {
          path: "runs",
          element: <RunsPage />,
        },
        {
          path: "runs/:runId",
          element: <RunDetailPage />,
        },
        {
          path: "runs/compare",
          element: <RunComparePage />,
        },
        {
          path: "scenarios",
          element: <ScenarioPage />,
        },
        {
          path: "validation",
          element: <ValidationSessionsPage />,
        },
        {
          path: "kg",
          element: <KnowledgeGraphOverviewPage />,
        },
        {
          path: "kg/runs/:runId",
          element: <RunPathGraphPage />,
        },
        {
          path: "guide",
          element: <GuidePage />,
        },
        {
          path: "settings/llm",
          element: <LlmSettingsPage />,
        },
      ],
    },
  ],
  {
    future: {
      v7_startTransition: true,
      v7_relativeSplatPath: true,
    },
  },
);
