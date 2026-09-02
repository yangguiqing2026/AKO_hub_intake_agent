import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, createRestClient } from "./rest";

describe("createRestClient", () => {
  beforeEach(() => { vi.stubGlobal("fetch", vi.fn()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("携带 Bearer 头并解析 JSON", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ok: 1 }), { status: 200 }));
    const client = createRestClient({ baseUrl: "http://x", getToken: () => "tok", onUnauthorized: vi.fn() });
    await expect(client.get<{ ok: number }>("/api/v1/bootstrap")).resolves.toEqual({ ok: 1 });
    expect(fetch).toHaveBeenCalledWith("http://x/api/v1/bootstrap", expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer tok" }) }));
  });

  it("401 → ApiError 并触发 onUnauthorized", async () => {
    const onUnauthorized = vi.fn();
    vi.mocked(fetch).mockResolvedValue(new Response("", { status: 401 }));
    const client = createRestClient({ baseUrl: "http://x", getToken: () => "tok", onUnauthorized });
    await expect(client.get("/api/v1/intake/sessions")).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalled();
  });

  it("POST 序列化 body", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response("{}", { status: 200 }));
    const client = createRestClient({ baseUrl: "http://x", getToken: () => "", onUnauthorized: vi.fn() });
    await client.post("/api/v1/identity/login", { account: "a", fingerprint: "123456" });
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(JSON.parse(init!.body as string)).toEqual({ account: "a", fingerprint: "123456" });
  });
});
