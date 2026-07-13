import { env } from "../../config/env.js";
import { BaseProvider } from "./base.js";
import type { AuthStyle, Capability } from "./types.js";

// Anthropic (x-api-key + /v1/messages).
export class AnthropicProvider extends BaseProvider {
  readonly id = "anthropic";
  readonly defaultBaseUrl = "https://api.anthropic.com";
  override readonly authStyle: AuthStyle = "x-api-key";

  override envKey() {
    return env.ANTHROPIC_API_KEY;
  }
  protected override envBaseUrl() {
    return env.ANTHROPIC_BASE_URL;
  }
  override inferFromModel(model: string) {
    return model.toLowerCase().startsWith("claude");
  }
  protected override authHeaders(token: string) {
    return { "x-api-key": token, "anthropic-version": "2023-06-01" };
  }
  protected override endpointFor(capability: Capability): string {
    switch (capability) {
      case "messages":
        return "/v1/messages";
      case "models":
        return "/v1/models";
      default:
        throw new Error(`anthropic: unsupported capability '${capability}'`);
    }
  }
}

export const anthropicProvider = new AnthropicProvider();
