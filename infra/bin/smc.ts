import { resolve } from "node:path";

import { App } from "aws-cdk-lib";

import { SmcStack } from "../lib/smc-stack";

// The CDK app: one stack in the region cdk.json names. What it serves is set
// in cdk.json's context, or with -c on the command line:
//
//   npx cdk deploy -c atlases='["cabinet-manual"]' -c viewSets='["cabinet-manual-test"]'
//
// A cost budget with an email alert is set only when an address is given:
//
//   npx cdk deploy -c budgetEmail=you@example.com -c budgetUsd=30

const app = new App();
const context = (key: string) => app.node.tryGetContext(key) as unknown;
const list = (key: string): string[] => {
  const value = context(key);
  const parsed: unknown = typeof value === "string" ? JSON.parse(value) : value;
  if (!Array.isArray(parsed) || !parsed.every((item) => typeof item === "string")) {
    throw new Error(`context ${key} must be a list of names`);
  }
  return parsed;
};

const number = (key: string): number => {
  const value = Number(context(key));
  if (!Number.isFinite(value) || value <= 0) throw new Error(`context ${key} must be a positive number`);
  return value;
};
const budgetEmail = context("budgetEmail");

new SmcStack(app, "SpatialMaintenanceCopilot", {
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: String(context("region")) },
  description: "Spatial Maintenance Copilot: web app, perception service and agent",
  root: resolve(__dirname, "..", ".."),
  atlases: list("atlases"),
  viewSets: list("viewSets"),
  model: String(context("model")),
  modelCallsPerDay: number("modelCallsPerDay"),
  budget: typeof budgetEmail === "string" && budgetEmail ? { usd: number("budgetUsd"), email: budgetEmail } : undefined,
});
