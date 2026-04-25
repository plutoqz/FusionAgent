import { screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { renderWithProviders } from "../../test/test-utils";
import { LlmSettingsPage } from "./LlmSettingsPage";

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

test("默认展示模型设置表单与掩码密钥状态", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

      if (url.endsWith("/api/v2/settings/llm/validate")) {
        return new Response(
          JSON.stringify({
            valid: true,
            settings: {
              provider: "openai",
              base_url: "https://api.openai.com/v1",
              model: "gpt-5.4-mini",
              timeout_sec: 60,
              has_api_key: true,
              api_key_masked: "sk-t...1234",
            },
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      if (init?.method === "PUT") {
        return new Response(
          JSON.stringify({
            provider: "openai",
            base_url: "https://api.openai.com/v1",
            model: "gpt-5.4-mini",
            timeout_sec: 60,
            has_api_key: true,
            api_key_masked: "sk-t...1234",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      return new Response(
        JSON.stringify({
          provider: "openai",
          base_url: "https://api.openai.com/v1",
          model: "gpt-5.4-mini",
          timeout_sec: 60,
          has_api_key: true,
          api_key_masked: "sk-t...1234",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    }),
  );

  renderWithProviders(<LlmSettingsPage />);

  expect(await screen.findByLabelText(/基础地址/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/api 密钥/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /校验连接/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /保存并应用/i })).toBeInTheDocument();
});
