import { expect, test } from "@playwright/test";

const obviousRuntimeErrors = /Application error|Unhandled Runtime Error|Build Error|Failed to compile|Module not found/i;

async function mockPublicBackend(page) {
  await page.route("**/proposals?**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 2177001,
          title: "Smoke proposal from Playwright",
          text: "A public signed-out feed item rendered from a mocked local backend response.",
          userName: "smoke-human",
          userInitials: "SH",
          author_type: "human",
          time: new Date("2026-05-05T00:00:00Z").toISOString(),
          media: {
            image: "",
            images: [],
            layout: "carousel",
            governance: null,
            video: "",
            link: "",
            file: "",
          },
          comments: [],
          likes: [],
          dislikes: [],
        },
      ]),
    });
  });

  await page.route("**/system-vote**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        question: "Should SuperNova keep public smoke tests advisory?",
        deadline: "2099-01-01T00:00:00Z",
        likes: [],
        dislikes: [],
        user_vote: null,
      }),
    });
  });
}

test("signed-out home feed renders without obvious runtime errors", async ({ page }) => {
  await mockPublicBackend(page);
  await page.goto("/");

  await expect(page.getByText("smoke-human")).toBeVisible();
  await expect(
    page.getByText("A public signed-out feed item rendered from a mocked local backend response.")
  ).toBeVisible();
  await expect(page.locator("body")).not.toContainText(obviousRuntimeErrors);
});

test("about page route renders the standalone page", async ({ page }) => {
  await page.goto("/about");

  await expect(page).toHaveTitle(/SuperNova 2177/i);
  await expect(page.locator("body")).toContainText(/Human/i);
  await expect(page.locator("body")).toContainText(/Organization/i);
  await expect(page.locator("body")).not.toContainText(obviousRuntimeErrors);
});
