import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderAt } from "../test/renderApp";

describe("pages", () => {
  it("dashboard shows stats and recent investigations", async () => {
    renderAt("/");
    expect(await screen.findByRole("heading", { level: 1, name: "Overview" })).toBeInTheDocument();
    expect(await screen.findByText("Total resources")).toBeInTheDocument();
    expect(screen.getByText("Active investigations")).toBeInTheDocument();
    expect(await screen.findByText(/failing status checks/)).toBeInTheDocument();
  });

  it("navigation renders every page", async () => {
    const user = userEvent.setup();
    renderAt("/");
    const nav = screen.getByRole("complementary");
    for (const [link, heading] of [
      ["AI Assistant", "AI Assistant"],
      ["Investigations", "Investigation history"],
      ["Infrastructure", "Infrastructure"],
      ["AWS Connections", "AWS connections"],
      ["Settings", "Settings"],
    ]) {
      await user.click(within(nav).getByRole("link", { name: link }));
      expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
    }
  });

  it("history filters by search text", async () => {
    const user = userEvent.setup();
    renderAt("/investigations");
    expect(await screen.findByText(/Lambda order-processor/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Search investigations"), "payments");
    await waitFor(() => expect(screen.queryByText(/Lambda order-processor/)).not.toBeInTheDocument());
    expect(screen.getByText(/payments-api stuck/)).toBeInTheDocument();
  });

  it("investigation details separate facts, hypotheses and recommendations, linked to evidence", async () => {
    const user = userEvent.setup();
    renderAt("/investigations/inv-1042");
    expect(await screen.findByText("Observed Facts")).toBeInTheDocument();
    expect(screen.getByText("Potential Root Causes")).toBeInTheDocument();
    expect(screen.getByText("Recommendations")).toBeInTheDocument();
    expect(screen.getByText("Confidence and limitations")).toBeInTheDocument();
    expect(screen.getAllByText("Observed Fact")).toHaveLength(5);
    expect(screen.getByText("86% confidence")).toBeInTheDocument();
    expect(screen.queryByText("Input")).not.toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "te-2" })[0]);
    const row = await screen.findByText("ec2_get_status_checks");
    expect(row.closest("tr")).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Input")).toBeInTheDocument();
    expect(screen.getByText(/"impaired"/)).toBeInTheDocument();
  });

  it("failed investigation explains the failure", async () => {
    renderAt("/investigations/inv-1038");
    expect(await screen.findByRole("alert")).toHaveTextContent(/Investigation failed.*sts:AssumeRole was denied/);
  });

  it("add-connection form validates and refuses access keys", async () => {
    const user = userEvent.setup();
    renderAt("/connections");
    await user.click(await screen.findByRole("button", { name: /Add connection/ }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Add connection" }));
    expect(within(dialog).getByText("Name is required.")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("External ID (optional)"), "AKIAABCDEFGHIJKLMNOP");
    expect(within(dialog).getByRole("alert")).toHaveTextContent(/never accepts long-lived keys/);
  });

  it("assistant starts an investigation in the selected scope", async () => {
    const user = userEvent.setup();
    renderAt("/assistant");
    await screen.findAllByRole("option", { name: /Production/ });
    await user.click(screen.getByRole("button", { name: /Find unhealthy EC2 instances/ }));
    expect(screen.getByLabelText("Investigation request")).toHaveValue("Find unhealthy EC2 instances in my AWS account.");
    await user.click(screen.getByRole("button", { name: /Send/ }));
    const progress = await screen.findByRole("list", { name: "Investigation progress" });
    await waitFor(() => expect(within(progress).getByText("Investigation queued.")).toBeInTheDocument());
    expect(screen.getByText(/auto-discovery/)).toBeInTheDocument();
  });

  it("infrastructure lists discovered resources and hands one to the assistant", async () => {
    const user = userEvent.setup();
    renderAt("/infrastructure");
    expect(await screen.findByText("api-worker-3")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /Lambda/ }));
    expect(screen.queryByText("api-worker-3")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Investigate order-processor" }));
    expect(await screen.findByLabelText("Investigation request")).toHaveValue("Investigate the health of Lambda function order-processor.");
  });
});
