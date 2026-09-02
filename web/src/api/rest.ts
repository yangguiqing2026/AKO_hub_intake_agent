export class ApiError extends Error {
  constructor(public readonly code: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export interface RestClientOptions {
  baseUrl: string;
  getToken: () => string;
  onUnauthorized?: () => void;
}

export function createRestClient(opts: RestClientOptions): { get: <T>(path: string) => Promise<T>; post: <T>(path: string, body?: unknown) => Promise<T> } {
  async function request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const token = opts.getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${opts.baseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.status === 401) {
      opts.onUnauthorized?.();
      throw new ApiError(401, "AUTH_REQUIRED");
    }
    if (!res.ok) throw new ApiError(res.status, await res.text().catch(() => ""));
    return (await res.json()) as T;
  }
  return {
    get: <T>(path: string): Promise<T> => request<T>("GET", path),
    post: <T>(path: string, body?: unknown): Promise<T> => request<T>("POST", path, body),
  };
}

export type RestClient = ReturnType<typeof createRestClient>;
