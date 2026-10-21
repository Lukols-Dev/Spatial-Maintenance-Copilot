import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { App } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import { ContainerImage } from "aws-cdk-lib/aws-ecs";
import { beforeAll, describe, expect, it } from "vitest";

import { SmcStack, workspaceSources } from "../lib/smc-stack";

// The stack's template, synthesized from a small workspace in a temporary
// folder and a public image, so nothing is built and nothing reaches AWS.

function workspace(withSite: boolean): string {
  const root = mkdtempSync(join(tmpdir(), "smc-infra-"));
  const file = (path: string, text: string) => {
    mkdirSync(join(root, path, ".."), { recursive: true });
    writeFileSync(join(root, path), text);
  };
  file("calib/intrinsics/phone.yml", "%YAML:1.0\n");
  file("calib/rig.yaml", "dictionary: DICT_5X5_100\n");
  file("data/atlas/cabinet-manual.json", "{}");
  file("data/views/cabinet-manual-test/clicks.json", "{}");
  if (withSite) file("apps/web/out/index.html", "<!doctype html>");
  return root;
}

function synth(withSite = true, budget?: { usd: number; email: string }): Template {
  const app = new App();
  const stack = new SmcStack(app, "Test", {
    env: { account: "123456789012", region: "eu-north-1" },
    root: workspace(withSite),
    atlases: ["cabinet-manual"],
    viewSets: ["cabinet-manual-test"],
    model: "eu.amazon.nova-2-lite-v1:0",
    modelCallsPerDay: 1000,
    budget,
    image: ContainerImage.fromRegistry("public.ecr.aws/docker/library/python:3.14-slim"),
  });
  return Template.fromStack(stack);
}

let template: Template;
beforeAll(() => {
  template = synth();
});

describe("the service", () => {
  it("runs on Graviton, read-only, signed by its task role and with no key", () => {
    template.hasResourceProperties("AWS::ECS::TaskDefinition", {
      RuntimePlatform: { CpuArchitecture: "ARM64", OperatingSystemFamily: "LINUX" },
    });
    const task = Object.values(template.findResources("AWS::ECS::TaskDefinition"))[0];
    const environment = Object.fromEntries(
      task.Properties.ContainerDefinitions[0].Environment.map((variable: { Name: string; Value: unknown }) => [
        variable.Name,
        variable.Value,
      ]),
    );
    expect(environment).toMatchObject({
      SMC_AWS_AUTH: "role",
      SMC_READ_ONLY: "true",
      SMC_ENV_FILE: "",
      SMC_AGENT_MODEL: "eu.amazon.nova-2-lite-v1:0",
      SMC_BEDROCK_REGION: "eu-north-1",
      SMC_MODEL_CALLS_PER_DAY: "1000",
    });
    expect(environment).not.toHaveProperty("AWS_ACCESS_KEY_ID");
    expect(environment).not.toHaveProperty("AWS_SECRET_ACCESS_KEY");
  });

  it("may call only the agent's model on Bedrock", () => {
    template.hasResourceProperties("AWS::IAM::Policy", {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            Resource: [
              "arn:aws:bedrock:eu-north-1:123456789012:inference-profile/eu.amazon.nova-2-lite-v1:0",
              "arn:aws:bedrock:*::foundation-model/amazon.nova-2-lite-v1:0",
            ],
          }),
        ]),
      },
    });
  });

  it("is reached through an internal load balancer only", () => {
    template.hasResourceProperties("AWS::ElasticLoadBalancingV2::LoadBalancer", { Scheme: "internal" });
    template.hasResourceProperties("AWS::ElasticLoadBalancingV2::TargetGroup", {
      HealthCheckPath: "/health",
      Port: 8000,
    });
  });

  it("describes its network rules only in the characters EC2 takes", () => {
    // EC2 refuses any other character, an apostrophe among them, and only once a deployment reaches the rule.
    const allowed = /^[\w. :/()#,@[\]+=&;{}!$*-]{0,255}$/;
    const groups = Object.values(template.findResources("AWS::EC2::SecurityGroup"));
    const rules = [
      ...Object.values(template.findResources("AWS::EC2::SecurityGroupIngress")).map((rule) => rule.Properties),
      ...groups.flatMap((group) => [...(group.Properties.SecurityGroupIngress ?? []), ...(group.Properties.SecurityGroupEgress ?? [])]),
    ] as { Description?: unknown }[];
    const descriptions = [...groups.map((group) => group.Properties.GroupDescription), ...rules.map((rule) => rule.Description)];

    expect(rules.length).toBeGreaterThan(0);
    for (const description of descriptions.filter((text) => typeof text === "string")) expect(description).toMatch(allowed);
  });
});

describe("the data", () => {
  it("keeps sessions in DynamoDB, keyed as the LangGraph saver writes them, expiring by ttl", () => {
    template.hasResourceProperties("AWS::DynamoDB::GlobalTable", {
      KeySchema: [
        { AttributeName: "PK", KeyType: "HASH" },
        { AttributeName: "SK", KeyType: "RANGE" },
      ],
      TimeToLiveSpecification: { AttributeName: "ttl", Enabled: true },
    });
  });

  it("keeps every bucket private", () => {
    const buckets = template.findResources("AWS::S3::Bucket");
    expect(Object.keys(buckets)).toHaveLength(2);
    for (const bucket of Object.values(buckets)) {
      expect(bucket.Properties.PublicAccessBlockConfiguration).toEqual({
        BlockPublicAcls: true,
        BlockPublicPolicy: true,
        IgnorePublicAcls: true,
        RestrictPublicBuckets: true,
      });
    }
  });

  it("copies the camera, the rig, the chosen atlases and view sets, and refuses one that is not there", () => {
    const root = workspace(false);
    const prefixes = workspaceSources({ root, atlases: ["cabinet-manual"], viewSets: ["cabinet-manual-test"] }).map(
      (source) => source.prefix,
    );
    expect(prefixes).toEqual(["calib/intrinsics", "calib", "data/atlas", "data/views/cabinet-manual-test"]);
    expect(() => workspaceSources({ root, atlases: ["nope"], viewSets: [] })).toThrow("no atlas nope");
    expect(() => workspaceSources({ root, atlases: [], viewSets: ["nope"] })).toThrow("no view set nope");
  });
});

describe("the web app", () => {
  it("is served by CloudFront, the API under /api without caching", () => {
    template.hasResourceProperties("AWS::CloudFront::Distribution", {
      DistributionConfig: Match.objectLike({
        DefaultRootObject: "index.html",
        CacheBehaviors: [
          Match.objectLike({
            PathPattern: "/api/*",
            AllowedMethods: Match.arrayWith(["PUT", "POST"]),
            CachePolicyId: "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
          }),
        ],
      }),
    });
  });

  it("routes /api/{proxy+} to the service's own paths, throttled", () => {
    template.hasResourceProperties("AWS::ApiGatewayV2::Route", { RouteKey: "ANY /api/{proxy+}" });
    template.hasResourceProperties("AWS::ApiGatewayV2::Integration", {
      ConnectionType: "VPC_LINK",
      RequestParameters: { "overwrite:path": "/$request.path.proxy" },
    });
    template.hasResourceProperties("AWS::ApiGatewayV2::Stage", {
      StageName: "$default",
      DefaultRouteSettings: { ThrottlingRateLimit: 20, ThrottlingBurstLimit: 40 },
    });
  });

  it("is uploaded only once it has been built", () => {
    // The camera, the rig, the atlas and the view set, then the site.
    expect(Object.keys(template.findResources("Custom::CDKBucketDeployment"))).toHaveLength(5);
    expect(Object.keys(synth(false).findResources("Custom::CDKBucketDeployment"))).toHaveLength(4);
  });
});

describe("the cost", () => {
  it("has no budget unless an address is given for its alerts", () => {
    template.resourceCountIs("AWS::Budgets::Budget", 0);
  });

  it("tells by email when the month's cost passes 80 % of the budget, or is forecast to pass it", () => {
    const budgeted = synth(true, { usd: 30, email: "owner@example.com" });

    budgeted.hasResourceProperties("AWS::Budgets::Budget", {
      Budget: { BudgetType: "COST", TimeUnit: "MONTHLY", BudgetLimit: { Amount: 30, Unit: "USD" } },
      NotificationsWithSubscribers: [
        {
          Notification: { NotificationType: "ACTUAL", Threshold: 80, ThresholdType: "PERCENTAGE" },
          Subscribers: [{ SubscriptionType: "EMAIL", Address: "owner@example.com" }],
        },
        {
          Notification: { NotificationType: "FORECASTED", Threshold: 100, ThresholdType: "PERCENTAGE" },
          Subscribers: [{ SubscriptionType: "EMAIL", Address: "owner@example.com" }],
        },
      ],
    });
  });
});
