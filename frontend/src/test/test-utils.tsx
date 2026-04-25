import "@testing-library/jest-dom/vitest";
import { ReactElement } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render } from "@testing-library/react";

import { I18nProvider } from "../app/i18n";
import { createQueryClient } from "../lib/query";

type RenderWithProvidersOptions = {
  path?: string;
  route?: string;
};

export function renderWithProviders(
  ui: ReactElement,
  { path = "/", route = "/" }: RenderWithProvidersOptions = {},
) {
  const queryClient = createQueryClient();

  return render(
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
          initialEntries={[route]}
        >
          <Routes>
            <Route path={path} element={ui} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </I18nProvider>,
  );
}
