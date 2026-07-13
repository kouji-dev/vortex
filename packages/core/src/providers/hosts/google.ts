import { env } from "../../config/env.js";
import { BaseProvider } from "./base.js";
import type { AuthStyle, Capability } from "./types.js";

// Google AI Studio (query key + generateContent).
export class GoogleProvider extends BaseProvider {
  readonly id = "google";
  readonly defaultBaseUrl = "https://generativelanguage.googleapis.com";
  override readonly authStyle: AuthStyle = "query";

  override envKey() {
    return env.GOOGLE_API_KEY;
  }
  protected override envBaseUrl() {
    return env.GOOGLE_BASE_URL;
  }
  override inferFromModel(model: string) {
    return model.toLowerCase().startsWith("gemini");
  }
  // Google auth key is passed as a `?key=` query param by the base resolver.
  protected override authHeaders() {
    return {};
  }
  protected override endpointFor(
    capability: Capability,
    streaming: boolean,
  ): string {
    switch (capability) {
      case "chat":
        return streaming
          ? "/v1beta/models/{model}:streamGenerateContent"
          : "/v1beta/models/{model}:generateContent";
      case "embeddings":
        return "/v1beta/models/{model}:embedContent";
      case "models":
        return "/v1beta/models";
      default:
        throw new Error(`google: unsupported capability '${capability}'`);
    }
  }
}

export const googleProvider = new GoogleProvider();
