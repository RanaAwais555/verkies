import { expect, test, type Page } from "@playwright/test";

import { ADMIN } from "./env";

// Slice 7.4 made the Viewer read-only in the API; the screens now hide what it would refuse
// instead of offering it and failing. Runs last: by now Harbour Immigration Ltd is a client with a
// deal, a project, tasks and documents (phases 3 and 4).
const VIEWER = { email: "vic@verkies.test", name: "Vic Viewer", password: "vic correct horse battery" };

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();
}

test("a viewer sees everything and is offered nothing they cannot do", async ({ page, browser }) => {
  await signIn(page, ADMIN.email, ADMIN.password);
  await page.goto("/settings");
  await page.getByRole("tab", { name: "Team" }).click();
  await page.getByLabel("Email").fill(VIEWER.email);
  await page.getByRole("checkbox", { name: "Viewer" }).first().check();
  await page.getByRole("button", { name: "Create invite link" }).click();
  const link = (await page.getByTestId("invite-link").locator("code").textContent())!.trim();

  const vic = await (await browser.newContext()).newPage();
  await vic.goto(link.replace(/^https?:\/\/[^/]+/, ""));
  await vic.getByLabel("Your name").fill(VIEWER.name);
  await vic.getByLabel(/^Password/).fill(VIEWER.password);
  await vic.getByLabel("Confirm password").fill(VIEWER.password);
  await vic.getByRole("button", { name: "Create account" }).click();
  await expect(vic.getByTestId("signed-in-as")).toHaveText(VIEWER.name);
  await expect(vic.getByTestId("view-only")).toBeVisible();

  // The account: every record is there to read, and nothing offers a change.
  await vic.goto("/accounts");
  await vic.getByLabel("Search accounts").fill("harbour");
  await vic.getByTestId("accounts").getByRole("link", { name: "Harbour Immigration Ltd" }).click();
  await expect(vic.getByTestId("contacts")).toBeVisible();
  for (const name of ["Add person", "Log activity", "Set next action", "Give feedback", "Convert to client"]) {
    await expect(vic.getByRole("button", { name })).toHaveCount(0);
  }
  await expect(vic.getByRole("button", { name: /^(Edit|Email|Enrol) / })).toHaveCount(0);

  await vic.getByRole("tab", { name: "Activities" }).click();
  await expect(vic.getByRole("heading", { name: "Logged activity" })).toBeVisible();
  await expect(vic.getByRole("heading", { name: "Log activity" })).toHaveCount(0);

  await vic.getByRole("tab", { name: /Tasks/ }).click();
  await expect(vic.getByTestId("task").first()).toBeVisible();
  await expect(vic.getByRole("button", { name: "Add task" })).toHaveCount(0);
  await expect(vic.getByRole("button", { name: "Mark done" })).toHaveCount(0);
  await expect(vic.getByText("Reassign or reschedule")).toHaveCount(0);

  await vic.getByRole("tab", { name: "Documents" }).click();
  await expect(vic.getByTestId("documents")).toBeVisible();
  await expect(vic.getByRole("button", { name: "Upload" })).toHaveCount(0);
  await expect(vic.getByRole("button", { name: /^Remove / })).toHaveCount(0);

  await vic.getByRole("tab", { name: "Client" }).click();
  await expect(vic.getByTestId("client-health")).toContainText("Red");
  for (const name of ["Record feedback", "No longer a client", "New project", "Log a referral they gave"]) {
    await expect(vic.getByRole("button", { name })).toHaveCount(0);
  }
  await expect(vic.getByLabel("Account manager")).toBeDisabled();

  // Watching is the viewer's own, so it stays; checking now does not.
  await vic.getByRole("button", { name: "Watch", exact: true }).click();
  await expect(vic.getByRole("button", { name: "Stop watching" })).toBeVisible();
  await expect(vic.getByRole("button", { name: "Check now" })).toHaveCount(0);
  await vic.getByRole("button", { name: "Stop watching" }).click();
  await expect(vic.getByRole("button", { name: "Watch", exact: true })).toBeVisible();

  // The board: deals are read, not moved; the deal panel shows its fields without Save.
  await vic.getByRole("link", { name: "Pipeline", exact: true }).click();
  const deal = vic.getByTestId("deal").first();
  await expect(deal).toBeVisible();
  await expect(deal).toHaveAttribute("draggable", "false");
  await expect(vic.getByLabel(/^Move .* to$/)).toHaveCount(0);
  await deal.getByRole("button").first().click();
  const panel = vic.getByTestId("deal-panel");
  await expect(panel.getByLabel("Deal name")).toBeDisabled();
  await expect(panel.getByRole("button", { name: "Save deal" })).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "Add next task" })).toHaveCount(0);

  // A project: milestones and risks to read; nothing to tick, raise or save.
  await vic.getByRole("link", { name: "Projects", exact: true }).click();
  await vic.getByTestId("project-row").filter({ hasText: "Harbour Immigration Ltd" }).getByRole("link").first().click();
  await expect(vic.getByTestId("milestones")).toContainText("Designs signed off");
  await expect(vic.getByRole("checkbox", { name: /Designs signed off/ })).toBeDisabled();
  await expect(vic.getByLabel("New milestone")).toHaveCount(0);
  await expect(vic.getByRole("button", { name: "Raise a risk" })).toHaveCount(0);
  await expect(vic.getByTestId("project-details").getByLabel("Name")).toBeDisabled();
  await expect(vic.getByTestId("project-details").getByRole("button", { name: "Save" })).toHaveCount(0);

  // No mailbox to connect: a viewer does not send email.
  await vic.goto("/settings");
  await expect(vic.getByRole("tab", { name: "Profile" })).toBeVisible();
  await expect(vic.getByRole("tab", { name: "Mailbox" })).toHaveCount(0);
  await vic.context().close();
});
