import { expect, test, type Page } from "@playwright/test";

import { ADMIN, SITE_PORT } from "./env";

// The Phase 1 definition of done (master context §20, PRODUCT_SPEC.md §4), in a real browser
// against the real stack. Tests run in order and share the database.
test.describe.configure({ mode: "serial" });

async function signIn(page: Page, email = ADMIN.email, password = ADMIN.password) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();
}

async function research(page: Page, url: string) {
  await page.goto("/");
  await page.getByLabel("Company website").fill(url);
  await page.getByRole("button", { name: "Research" }).click();
  await expect(page).toHaveURL(/\/research\/[0-9a-f-]{36}$/);
  // Crawl progress is visible while the worker runs, then the brief replaces it.
  await expect(page.getByRole("tab", { name: "Lead brief" })).toBeVisible({ timeout: 90_000 });
}

test("signed-out visitors are sent to sign in, and come back after", async ({ page }) => {
  await page.goto("/accounts");
  await expect(page).toHaveURL(/\/login\?next=%2Faccounts$/);
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill("wrong password entirely");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/accounts$/);
  await expect(page.getByRole("heading", { name: "Accounts" })).toBeVisible();
});

test("an admin invites a teammate who joins with their own password", async ({ page, browser }) => {
  await signIn(page);
  await page.goto("/settings");
  await page.getByRole("tab", { name: "Team" }).click();
  await page.getByLabel("Email").fill("sam@verkies.test");
  await page.getByRole("checkbox", { name: "Salesperson" }).first().check();
  await page.getByRole("button", { name: "Create invite link" }).click();
  const link = (await page.getByTestId("invite-link").locator("code").textContent())!.trim();
  expect(link).toMatch(/\/invite#token=/);

  const sam = await (await browser.newContext()).newPage();
  await sam.goto(link.replace(/^https?:\/\/[^/]+/, ""));
  await expect(sam.getByText("Invited as")).toContainText("sam@verkies.test");
  await sam.getByLabel("Your name").fill("Sam Seller");
  await sam.getByLabel(/^Password/).fill("sam correct horse battery");
  await sam.getByLabel("Confirm password").fill("sam correct horse battery");
  await sam.getByRole("button", { name: "Create account" }).click();
  await expect(sam.getByTestId("signed-in-as")).toHaveText("Sam Seller");
  await expect(sam.getByRole("heading", { name: "Home" })).toBeVisible();
  await sam.context().close();
});

test("research a company, review the evidence and approve it into the CRM", async ({ page }) => {
  await signIn(page);
  await research(page, `http://harbour.test:${SITE_PORT}/`);

  // Lead brief: every claim class shown, evidence one click away, Unknown where there is none.
  const brief = page.getByTestId("brief");
  await expect(brief.getByRole("heading", { name: "Harbour Immigration Ltd" })).toBeVisible();
  await expect(brief.getByText("Qualifies", { exact: true })).toBeVisible();
  for (const section of ["Company overview", "Problem detected", "Why Verkies", "Why now", "Recommended service", "Best buyer", "Risks", "Recommended next action"]) {
    await expect(brief.getByRole("heading", { name: section, exact: true })).toBeVisible();
  }
  await expect(brief.locator('[data-class="fact"]').first()).toBeVisible();
  await expect(brief.locator('[data-class="inference"]').first()).toBeVisible();
  await expect(brief.locator('[data-class="recommendation"]').first()).toBeVisible();
  await brief.getByRole("button", { name: /Show evidence/ }).first().click();
  await expect(brief.getByRole("link", { name: /harbour\.test/ }).first()).toBeVisible();
  const similar = brief.locator("section", { has: page.getByRole("heading", { name: "Similar Verkies work" }) });
  await expect(similar.getByTestId("unknown")).toContainText("Unknown");

  // Opportunities, ICP and scores; then the raw intelligence and the crawled pages.
  await page.getByRole("tab", { name: "Opportunities and scores" }).click();
  await expect(page.getByRole("heading", { name: "Detected opportunities" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Qualification (ICP)" })).toBeVisible();
  await expect(page.getByText("ICP fit").first()).toBeVisible();
  await page.getByRole("tab", { name: "Intelligence" }).click();
  await expect(page.getByText("company.person").first()).toBeVisible();
  await page.getByRole("tab", { name: "Pages crawled" }).click();
  await expect(page.getByRole("link", { name: /\/our-team\/$/ })).toBeVisible();

  // Approve: Account, Lead, Opportunity, Contacts and the next-action Task in one go.
  await page.getByRole("button", { name: "Approve and create the account" }).click();
  await expect(page.getByTestId("approved")).toContainText("New account created");
  await page.getByRole("link", { name: "Open the account" }).click();

  await expect(page.getByRole("heading", { name: "Harbour Immigration Ltd" })).toBeVisible();
  await expect(page.getByText("Qualified prospect").first()).toBeVisible();
  await expect(page.getByTestId("contacts")).toContainText("Amelia Hart");
  await expect(page.getByTestId("contacts")).toContainText("Email unknown");
  await expect(page.getByTestId("opportunities")).toContainText("Website rebuild: Harbour Immigration Ltd");
  await page.getByRole("tab", { name: /^Tasks/ }).click();
  await expect(page.getByTestId("task")).toHaveCount(1);
  await page.getByRole("tab", { name: "Timeline" }).click();
  const timeline = page.getByTestId("timeline");
  await expect(timeline).toContainText("Account created from research on harbour.test");
  await expect(timeline).toContainText("Lead approved and qualified");
  await expect(timeline).toContainText("Contact Amelia Hart");
  await expect(timeline).toContainText("Task for Ada Admin");
  await page.getByRole("tab", { name: "Audit" }).click();
  await expect(page.getByTestId("audit")).toContainText("prospect.approved");

  // Back returns to the decided run, which shows the outcome instead of the decision buttons.
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await expect(page.getByTestId("approved")).toBeVisible();
  await expect(page.getByRole("group", { name: "Decision" })).toHaveCount(0);
  await page.getByRole("link", { name: "Back to the review queue" }).click();

  // The new task is on Home; completing it leaves the opportunity needing a next action,
  // which shows at once, without reloading the page.
  await expect(page.getByTestId("my-tasks").getByTestId("task")).toHaveCount(1);
  await expect(page.getByTestId("review-queue")).toHaveCount(0); // queue is empty now
  await page.getByRole("button", { name: "Mark done" }).click();
  await expect(page.getByText("No open tasks.")).toBeVisible();
  await expect(page.getByTestId("attention")).toContainText("next action is closed");

  // Setting a new, owned and dated next action clears it again.
  await page.getByTestId("attention").getByRole("link", { name: "Harbour Immigration Ltd" }).click();
  await page.getByRole("button", { name: "Set next action" }).click();
  const form = page.getByTestId("new-task");
  await form.getByLabel("What needs doing").fill("Call Amelia about client intake");
  await form.getByLabel("Due").fill("2030-01-15");
  await form.getByRole("button", { name: "Set next action" }).click();
  await expect(page.getByText("Requires attention")).toHaveCount(0);
  await page.goto("/");
  await expect(page.getByTestId("my-tasks")).toContainText("Call Amelia about client intake");
  await expect(page.getByText("Every opportunity has an owned, dated next action.")).toBeVisible();

  await page.goto("/accounts");
  await page.getByLabel("Search accounts").fill("harbour");
  await expect(page.getByTestId("accounts")).toContainText("Harbour Immigration Ltd");
});

test("reject a competitor: off the queue, still searchable", async ({ page }) => {
  await signIn(page);
  await research(page, `http://pixelforge.test:${SITE_PORT}/`);
  await expect(page.getByTestId("brief").getByText("Does not qualify")).toBeVisible();

  // The engines rejected it, so the decision panel opens on Reject with their reason chosen.
  await expect(page.getByLabel("Reason")).toHaveValue("competitor");
  await page.getByLabel("Note (optional)").fill("Agency, not a buyer");
  await page.getByRole("button", { name: "Reject", exact: true }).last().click();
  await expect(page.getByTestId("rejected")).toBeVisible();
  await expect(page.getByRole("group", { name: "Decision" })).toHaveCount(0);

  await page.getByRole("link", { name: "Back to the review queue" }).click();
  await expect(page.getByText("Nothing to review.")).toBeVisible();
  await page.goto("/research");
  await page.getByLabel("Review status").selectOption("rejected");
  await page.getByLabel("Search by domain").fill("pixel");
  const runs = page.getByTestId("runs");
  await expect(runs).toContainText("pixelforge.test");
  await expect(runs).toContainText("Competitor");
  await expect(runs).not.toContainText("harbour.test");
});
