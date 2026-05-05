import { expect, test } from "@playwright/test";

const obviousRuntimeErrors = /Application error|Unhandled Runtime Error|Build Error|Failed to compile|Module not found/i;
const backendBaseUrl = (
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.PLAYWRIGHT_API_URL ||
  "http://127.0.0.1:8000"
).replace(/\/+$/, "");

function escapeRegExp(value) {
  return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function readJson(request, path) {
  let response = null;
  try {
    response = await request.get(`${backendBaseUrl}${path}`, {
      failOnStatusCode: false,
      timeout: 7_000,
    });
  } catch (error) {
    return { response: null, body: null, error };
  }
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  return { response, body };
}

function visiblePostCandidates(posts) {
  return posts
    .flatMap((post) => [
      post?.userName,
      post?.username,
      post?.title,
      post?.text,
      post?.description,
    ])
    .map((value) => String(value || "").trim())
    .filter((value) => value.length >= 4)
    .slice(0, 12)
    .map((value) => value.slice(0, 80));
}

test.describe("real backend public reads", () => {
  test.skip(
    process.env.PLAYWRIGHT_REAL_BACKEND !== "1",
    "Set PLAYWRIGHT_REAL_BACKEND=1 with NEXT_PUBLIC_API_URL to run real-backend public smoke."
  );

  test("signed-out home renders against a real public backend", async ({ page, request }) => {
    const health = await readJson(request, "/health");
    test.skip(
      !health.response?.ok(),
      `Real backend unavailable at ${backendBaseUrl}/health; skipping advisory public-read smoke.`
    );

    const status = await readJson(request, "/supernova-status");
    expect(status.response.ok()).toBeTruthy();

    const feed = await readJson(request, "/proposals?filter=latest&limit=30");
    expect(feed.response.ok()).toBeTruthy();
    const posts = Array.isArray(feed.body) ? feed.body : [];

    await page.goto("/");
    const body = page.locator("body");
    await expect(body).not.toContainText(obviousRuntimeErrors);
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();

    const candidates = visiblePostCandidates(posts);
    if (posts.length === 0 || candidates.length === 0) {
      await expect(page.getByText("No posts yet.")).toBeVisible();
    } else {
      await expect(body).toContainText(new RegExp(candidates.map(escapeRegExp).join("|")));
    }
  });
});
