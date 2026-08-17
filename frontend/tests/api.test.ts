import { afterEach, describe, expect, it, vi } from "vitest";

import { api, request } from "../lib/api";
import { ClientError } from "../lib/errors";

function mockErrorResponse(status: number, body: unknown, contentType = "application/json") {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(contentType === "application/json" ? JSON.stringify(body) : String(body), {
        status,
        headers: { "Content-Type": contentType },
      }),
    ),
  );
}

describe("API errors", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each([
    [
      400,
      { message: "Invalid source", code: "invalid_source" },
      "Invalid source",
      "invalid_source",
    ],
    [404, { detail: "Episode not found" }, "Episode not found", undefined],
    [409, { message: "Import already exists" }, "Import already exists", undefined],
  ])("preserves a domain error returned with status %i", async (status, body, message, code) => {
    mockErrorResponse(status, body);

    await expect(api.getEpisode("episode-id")).rejects.toMatchObject({
      message,
      status,
      code,
    });
  });

  it("formats FastAPI validation details without object coercion", async () => {
    mockErrorResponse(422, {
      detail: [
        {
          type: "url_parsing",
          loc: ["body", "source", "url"],
          msg: "Input should be a valid URL",
        },
        {
          type: "missing",
          loc: ["body", "options", "language"],
          msg: "Field required",
        },
      ],
    });

    await expect(api.getEpisode("episode-id")).rejects.toMatchObject({
      message: "source.url: Input should be a valid URL; options.language: Field required",
      status: 422,
    });
  });

  it("falls back to the HTTP status for a non-JSON response", async () => {
    mockErrorResponse(502, "Bad gateway", "text/plain");

    await expect(api.getEpisode("episode-id")).rejects.toMatchObject({
      message: "HTTP request failed with status 502",
      status: 502,
    });
  });
});

describe("transcript API", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("encodes pagination, search and timestamp parameters", async () => {
    const body = {
      id: "transcript-id",
      version: 1,
      provider: "test",
      model: null,
      language: "pt",
      segment_count: 0,
      matched_count: 0,
      limit: 25,
      query: "alice",
      next_cursor: null,
      anchor_segment_id: null,
      segments: [],
    };
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await api.getTranscript("episode-id", {
      cursor: "cursor+/=",
      query: "alice",
      limit: 25,
      signal: controller.signal,
    });

    const [requestUrl, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    const url = new URL(requestUrl);
    expect(url.pathname).toBe("/v1/episodes/episode-id/transcript");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      cursor: "cursor+/=",
      q: "alice",
      limit: "25",
    });
    expect(requestInit.signal).toBe(controller.signal);

    await api.getTranscript("episode-id", { atMs: 12_500 });
    const timestampUrl = new URL(fetchMock.mock.calls[1][0] as string);
    expect(Object.fromEntries(timestampUrl.searchParams)).toEqual({ at_ms: "12500" });
  });
});

describe("episode list API", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("encodes limit, offset and abort signal", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          items: [],
          total: 0,
          active_count: 0,
          limit: 50,
          offset: 100,
        }),
        { headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await api.listEpisodes({ limit: 50, offset: 100, signal: controller.signal });

    const [requestUrl, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(Object.fromEntries(new URL(requestUrl).searchParams)).toEqual({
      limit: "50",
      offset: "100",
    });
    expect(requestInit.signal).toBe(controller.signal);
  });
});

describe("episode workspace API", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("passes abort signals to episode and job requests", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({}), {
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await api.getEpisode("episode-id", { signal: controller.signal });
    await api.getJob("job-id", { signal: controller.signal });
    await api.getPlayback("episode-id", { signal: controller.signal });

    expect((fetchMock.mock.calls[0][1] as RequestInit).signal).toBe(controller.signal);
    expect((fetchMock.mock.calls[1][1] as RequestInit).signal).toBe(controller.signal);
    expect(fetchMock.mock.calls[1][0]).toContain("/v1/jobs/job-id");
    expect(fetchMock.mock.calls[2][0]).toContain("/v1/episodes/episode-id/playback");
    expect((fetchMock.mock.calls[2][1] as RequestInit).signal).toBe(controller.signal);
  });

  it("omits content type from read requests without a body", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({}), {
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.listEpisodes();
    await api.getEpisode("episode-id");
    await api.getJob("job-id");
    await api.getTranscript("episode-id");
    await api.getPlayback("episode-id");
    await api.listSummaries("episode-id");

    expect(fetchMock).toHaveBeenCalledTimes(6);
    for (const [, init] of fetchMock.mock.calls as Array<[string, RequestInit]>) {
      expect(init.headers).toBeUndefined();
    }
  });

  it("adds JSON content type to writes and preserves explicit headers", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({}), {
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.createSummary("episode-id");
    await api.updateSpeaker("episode-id", "speaker-id", "Alice");
    await request("/v1/custom", {
      method: "POST",
      body: JSON.stringify({ value: true }),
      headers: {
        "Content-Type": "application/merge-patch+json",
        "X-Request-Source": "test",
      },
    });

    const createHeaders = new Headers((fetchMock.mock.calls[0][1] as RequestInit).headers);
    const updateHeaders = new Headers((fetchMock.mock.calls[1][1] as RequestInit).headers);
    const explicitHeaders = new Headers((fetchMock.mock.calls[2][1] as RequestInit).headers);
    expect(createHeaders.get("Content-Type")).toBe("application/json");
    expect(updateHeaders.get("Content-Type")).toBe("application/json");
    expect(explicitHeaders.get("Content-Type")).toBe("application/merge-patch+json");
    expect(explicitHeaders.get("X-Request-Source")).toBe("test");
  });
});

describe("direct uploads", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts the signed policy fields and file as multipart form data", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["audio"], "episode.mp3", { type: "audio/mpeg" });

    await api.uploadObject(
      "https://storage.example/upload",
      {
        key: "workspace/uploads/id/episode.mp3",
        "Content-Type": "audio/mpeg",
        "x-amz-meta-expected-size": String(file.size),
      },
      file,
    );

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://storage.example/upload");
    expect(init.method).toBe("POST");
    expect(init.headers).toBeUndefined();
    const form = init.body as FormData;
    expect(form.get("key")).toBe("workspace/uploads/id/episode.mp3");
    expect(form.get("Content-Type")).toBe("audio/mpeg");
    expect(form.get("x-amz-meta-expected-size")).toBe(String(file.size));
    expect(form.get("file")).toBe(file);
  });

  it("sends a concrete media MIME type to upload and import APIs", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            object_key: "workspace/uploads/id/episode.mp4",
            upload_url: "https://storage.example/upload",
            method: "POST",
            fields: {},
          }),
          { headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ episode_id: "episode-id", job_id: "job-id" }), {
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["video"], "episode.mp4", { type: "video/mp4" });

    await api.initiateUpload(file);
    await api.createUploadImport("workspace/uploads/id/episode.mp4", file);

    const initiateBody = JSON.parse(
      String((fetchMock.mock.calls[0][1] as RequestInit).body),
    ) as Record<string, unknown>;
    const importBody = JSON.parse(String((fetchMock.mock.calls[1][1] as RequestInit).body)) as {
      source: Record<string, unknown>;
    };
    expect(initiateBody.content_type).toBe("video/mp4");
    expect(importBody.source.content_type).toBe("video/mp4");
  });

  it.each(["", "application/pdf"])(
    "rejects unsupported MIME type %j before making an API request",
    (contentType) => {
      const fetchMock = vi.fn();
      vi.stubGlobal("fetch", fetchMock);
      const file = new File(["media"], "episode.bin", { type: contentType });

      expect(() => api.initiateUpload(file)).toThrowError(ClientError);
      expect(() => api.initiateUpload(file)).toThrow("unsupported_media_type");
      expect(() => api.createUploadImport("workspace/uploads/id/episode.bin", file)).toThrowError(
        ClientError,
      );
      expect(() => api.createUploadImport("workspace/uploads/id/episode.bin", file)).toThrow(
        "unsupported_media_type",
      );
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );
});

describe("import options", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each(["spotify", "apple"] as const)(
    "sends an optional RSS hint for %s imports",
    async (sourceType) => {
      const fetchMock = vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ episode_id: "episode-id", job_id: "job-id" }), {
          headers: { "Content-Type": "application/json" },
        }),
      );
      vi.stubGlobal("fetch", fetchMock);

      await api.createUrlImport(
        sourceType,
        "https://podcast.example/episode",
        "",
        "pt",
        "https://podcast.example/feed.xml",
      );

      const body = JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body)) as {
        source: Record<string, unknown>;
      };
      expect(body.source.rss_url_hint).toBe("https://podcast.example/feed.xml");
    },
  );

  it.each(["rss", "direct_url"] as const)(
    "drops an RSS hint for %s imports",
    async (sourceType) => {
      const fetchMock = vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ episode_id: "episode-id", job_id: "job-id" }), {
          headers: { "Content-Type": "application/json" },
        }),
      );
      vi.stubGlobal("fetch", fetchMock);

      await api.createUrlImport(
        sourceType,
        "https://podcast.example/episode",
        "",
        "pt",
        "https://stale.example/feed.xml",
      );

      const body = JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body)) as {
        source: Record<string, unknown>;
      };
      expect(body.source.rss_url_hint).toBeNull();
    },
  );

  it("disables diarization for URL and upload imports", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ episode_id: "episode-id", job_id: "job-id" }), {
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["audio"], "episode.mp3", { type: "audio/mpeg" });

    await api.createUrlImport("rss", "https://podcast.example/feed.xml");
    await api.createUploadImport("workspace/uploads/id/episode.mp3", file);

    const urlBody = JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body)) as {
      options: Record<string, unknown>;
    };
    const uploadBody = JSON.parse(String((fetchMock.mock.calls[1][1] as RequestInit).body)) as {
      options: Record<string, unknown>;
    };
    expect(urlBody.options.diarization).toBe(false);
    expect(uploadBody.options.diarization).toBe(false);
  });
});
