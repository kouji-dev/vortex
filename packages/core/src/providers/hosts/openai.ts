import { env } from "../../config/env.js";
import { BaseProvider } from "./base.js";
import type { AuthStyle, Capability } from "./types.js";

// OpenAI-compatible group (bearer + /v1/chat/completions). openai + every OSS
// inference host (groq/mistral/deepseek/xai/together/…) are one class; embedding
// a new one is just id + base URL (+ env hooks).

interface OpenAICompatibleOpts {
  pathPrefix?: string; // for hosts not mounted under /v1
  envKey?: () => string | undefined;
  envBaseUrl?: () => string | undefined;
  inferMatch?: (model: string) => boolean;
}

export class OpenAICompatibleProvider extends BaseProvider {
  override readonly authStyle: AuthStyle = "bearer";
  constructor(
    readonly id: string,
    readonly defaultBaseUrl: string,
    private readonly opts: OpenAICompatibleOpts = {},
  ) {
    super();
  }

  override envKey(): string | undefined {
    return this.opts.envKey?.();
  }
  protected override envBaseUrl(): string | undefined {
    return this.opts.envBaseUrl?.();
  }
  override inferFromModel(model: string): boolean {
    return this.opts.inferMatch?.(model.toLowerCase()) ?? false;
  }

  protected override endpointFor(capability: Capability): string {
    const p = this.opts.pathPrefix ?? "/v1";
    switch (capability) {
      case "chat":
        return `${p}/chat/completions`;
      case "responses":
        return `${p}/responses`;
      case "embeddings":
        return `${p}/embeddings`;
      case "models":
        return `${p}/models`;
      default:
        throw new Error(`${this.id}: unsupported capability '${capability}'`);
    }
  }
}

export const openaiProvider = new OpenAICompatibleProvider(
  "openai",
  "https://api.openai.com",
  {
    envKey: () => env.OPENAI_API_KEY,
    envBaseUrl: () => env.OPENAI_BASE_URL,
    inferMatch: (m) =>
      m.startsWith("gpt") ||
      m.startsWith("chatgpt") ||
      m.startsWith("text-embedding") ||
      /^o[1-9]/.test(m), // o1 / o3 / o4 …
  },
);

// Most-used OpenAI-compatible inference providers. Bearer + /v1/chat/completions.
export const groqProvider = new OpenAICompatibleProvider(
  "groq",
  "https://api.groq.com/openai",
  { envKey: () => env.GROQ_API_KEY, envBaseUrl: () => env.GROQ_BASE_URL },
);
export const mistralProvider = new OpenAICompatibleProvider(
  "mistral",
  "https://api.mistral.ai",
  { envKey: () => env.MISTRAL_API_KEY, envBaseUrl: () => env.MISTRAL_BASE_URL },
);
export const deepseekProvider = new OpenAICompatibleProvider(
  "deepseek",
  "https://api.deepseek.com",
  { envKey: () => env.DEEPSEEK_API_KEY, envBaseUrl: () => env.DEEPSEEK_BASE_URL },
);
export const xaiProvider = new OpenAICompatibleProvider(
  "xai",
  "https://api.x.ai",
  { envKey: () => env.XAI_API_KEY, envBaseUrl: () => env.XAI_BASE_URL },
);
export const togetherProvider = new OpenAICompatibleProvider(
  "together",
  "https://api.together.xyz",
  { envKey: () => env.TOGETHER_API_KEY, envBaseUrl: () => env.TOGETHER_BASE_URL },
);
export const fireworksProvider = new OpenAICompatibleProvider(
  "fireworks",
  "https://api.fireworks.ai/inference",
  { envKey: () => env.FIREWORKS_API_KEY, envBaseUrl: () => env.FIREWORKS_BASE_URL },
);
