import { PropsWithChildren, useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";

import { I18nProvider } from "./i18n";
import { createQueryClient } from "../lib/query";

export function AppProviders({ children }: PropsWithChildren) {
  const [queryClient] = useState(() => createQueryClient());

  return (
    <I18nProvider>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </I18nProvider>
  );
}
