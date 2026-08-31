// Regression tests for API base-URL normalization.
//
// `NEXT_PUBLIC_API_BASE_URL` is supplied two different ways depending on how the
// app is deployed: as an origin for local dev (frontend and backend on separate
// ports) and as a same-origin path prefix for the single-image Docker/Render/Fly
// deploy. Both must resolve to exactly one "/api" segment — a "/api" prefix once
// produced requests to "/api/api/health", which 404'd every call in production.

import { afterEach, describe, expect, it, vi } from "vitest";

async function loadApi(base?: string) {
  vi.resetModules();
  if (base === undefined) {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "");
    // An empty string is a *set* value; delete it so the default path is taken.
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
  } else {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", base);
  }
  return import("./api");
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("API_ROOT", () => {
  it("appends /api to the local-dev origin default", async () => {
    const { API_ROOT } = await loadApi(undefined);
    expect(API_ROOT).toBe("http://localhost:8000/api");
  });

  it("appends /api to an explicit origin", async () => {
    const { API_ROOT } = await loadApi("https://agent.example.com");
    expect(API_ROOT).toBe("https://agent.example.com/api");
  });

  it("does not double up when the base is already the /api prefix", async () => {
    const { API_ROOT } = await loadApi("/api");
    expect(API_ROOT).toBe("/api");
  });

  it("does not double up when an origin already ends in /api", async () => {
    const { API_ROOT } = await loadApi("https://agent.example.com/api");
    expect(API_ROOT).toBe("https://agent.example.com/api");
  });

  it("strips trailing slashes before joining", async () => {
    const { API_ROOT } = await loadApi("https://agent.example.com///");
    expect(API_ROOT).toBe("https://agent.example.com/api");
  });

  it("treats an empty base as same-origin", async () => {
    const { API_ROOT } = await loadApi("");
    expect(API_ROOT).toBe("/api");
  });

  it("does not mistake a host ending in 'api' for the /api prefix", async () => {
    const { API_ROOT } = await loadApi("https://api.example.com");
    expect(API_ROOT).toBe("https://api.example.com/api");
  });
});
