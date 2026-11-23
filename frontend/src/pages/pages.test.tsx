import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderAt } from "../test/renderApp";

describe("pages", () => {
  it("dashboard shows stats and recent investigations", async () => {
    renderAt("/");
    expect(await screen.findByRole("heading", { name: "Operations overview" })).toBeInTheDocument();
    expect(await screen.findByText("Investigations (7 days)")).toBeInTheDocument();
    expect(await screen.findByText(/failing status checks/)).toBeInTheDocument();
  });

  it("navigation renders every page", async () => {
    const user = userEvent.setup();
    renderAt("/");
    const nav = screen.getByRole("complementary");
    for (const [link, heading] of [
      ["AI Assistant", "AI Assistant"],
      ["Investigations", "Investigation history"],
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
    expect(await screen.findByText("Observed conditions (facts)")).toBeInTheDocument();
    expect(screen.getByText("Potential root causes (hypotheses)")).toBeInTheDocument();
    expect(screen.getByText("Recommended troubleshooting steps")).toBeInTheDocument();
    expect(screen.getByText("Confidence and limitations")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "te-2" })[0]);
    expect(await screen.findByText(/Raw tool outputs exactly as returned/)).toBeInTheDocument();
    expect(screen.getAllByText("ec2_get_status_checks").length).toBeGreaterThan(0);
  });

  it("failed investigation explains the failure", async () => {
    renderAt("/investigations/inv-1038");
    expect(await screen.findByText(/sts:AssumeRole was denied/)).toBeInTheDocument();
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
    await user.click(screen.getByRole("button", { name: /^Investigate$/ }));
    const progress = await screen.findByRole("list", { name: "Investigation progress" });
    await waitFor(() => expect(within(progress).getByText("Investigation queued.")).toBeInTheDocument());
    expect(screen.getByText(/auto-discovery/)).toBeInTheDocument();
  });
});
