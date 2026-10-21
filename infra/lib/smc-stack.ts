import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { CfnOutput, Duration, RemovalPolicy, Stack, type StackProps } from "aws-cdk-lib";
import { HttpApi, HttpMethod, HttpStage, MappingValue, ParameterMapping, VpcLink } from "aws-cdk-lib/aws-apigatewayv2";
import { HttpAlbIntegration } from "aws-cdk-lib/aws-apigatewayv2-integrations";
import {
  AllowedMethods,
  CachePolicy,
  Distribution,
  Function as CloudFrontFunction,
  FunctionCode,
  FunctionEventType,
  OriginRequestPolicy,
  ViewerProtocolPolicy,
} from "aws-cdk-lib/aws-cloudfront";
import { CfnBudget } from "aws-cdk-lib/aws-budgets";
import { HttpOrigin, S3BucketOrigin } from "aws-cdk-lib/aws-cloudfront-origins";
import { Dashboard, GraphWidget, Metric } from "aws-cdk-lib/aws-cloudwatch";
import { AttributeType, Billing, TableV2 } from "aws-cdk-lib/aws-dynamodb";
import { Peer, Port, SecurityGroup, SubnetType, Vpc } from "aws-cdk-lib/aws-ec2";
import { Platform } from "aws-cdk-lib/aws-ecr-assets";
import {
  Cluster,
  ContainerImage,
  ContainerInsights,
  CpuArchitecture,
  FargateService,
  FargateTaskDefinition,
  LogDrivers,
  OperatingSystemFamily,
} from "aws-cdk-lib/aws-ecs";
import { ApplicationLoadBalancer, ApplicationProtocol } from "aws-cdk-lib/aws-elasticloadbalancingv2";
import { PolicyStatement } from "aws-cdk-lib/aws-iam";
import { LogGroup, RetentionDays } from "aws-cdk-lib/aws-logs";
import { BlockPublicAccess, Bucket, BucketEncryption } from "aws-cdk-lib/aws-s3";
import { BucketDeployment, Source, type ISource } from "aws-cdk-lib/aws-s3-deployment";
import type { Construct } from "constructs";

// Spatial Maintenance Copilot on AWS, the proposal's architecture (§8):
//
//   CloudFront ── /        → S3: the web app, a static export
//              └─ /api/*   → API Gateway (HTTP API) ─ VPC link → internal ALB → ECS Fargate (Graviton)
//
// The service reads its workspace (camera, rig, atlases, the view sets the demo
// shows) from a private S3 bucket at startup and runs read-only. Agent sessions
// live in DynamoDB. Bedrock calls are signed by the task role: no long-lived
// key is stored anywhere. Logs and a dashboard are in CloudWatch.

export interface SmcStackProps extends StackProps {
  /** The repository root: the web app's export, calib/ and data/ are read from there. */
  root: string;
  /** Atlases of data/atlas/ the deployment serves. */
  atlases: string[];
  /** View sets of data/views/ the deployment serves. */
  viewSets: string[];
  /** The agent's model on Bedrock: an inference profile of the stack's region. */
  model: string;
  /** Calls to the agent's and the vision model a UTC day, past which the agent uses the policy's words. */
  modelCallsPerDay: number;
  /** A monthly cost budget of the account, and who is told by email at 80 % of it and at forecast 100 %. */
  budget?: { usd: number; email: string };
  /** The service's image; by default built from services/perception/Dockerfile for ARM64. */
  image?: ContainerImage;
}

/** The port the service listens on in its container. */
const SERVICE_PORT = 8000;
/** Where the workspace is copied to in the container: the app user's home, which it may write. */
const CONTAINER_WORKSPACE = "/home/app/workspace";
const WORKSPACE_PREFIX = "workspace";

// The export has one index.html per page (/localise/index.html): CloudFront asks
// S3 for objects, so a page's path is completed to its file.
const INDEX_REWRITE = `
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  if (uri.endsWith("/")) request.uri = uri + "index.html";
  else if (!uri.split("/").pop().includes(".")) request.uri = uri + "/index.html";
  return request;
}`;

export class SmcStack extends Stack {
  constructor(scope: Construct, id: string, props: SmcStackProps) {
    super(scope, id, props);

    // ---- data ------------------------------------------------------------------

    const workspace = new Bucket(this, "Workspace", {
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
      encryption: BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      versioned: true,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });
    for (const [index, { source, prefix }] of workspaceSources(props).entries()) {
      new BucketDeployment(this, `WorkspaceFiles${index}`, {
        sources: [source],
        destinationBucket: workspace,
        destinationKeyPrefix: `${WORKSPACE_PREFIX}/${prefix}`,
        prune: false,
      });
    }

    const sessions = new TableV2(this, "Sessions", {
      partitionKey: { name: "PK", type: AttributeType.STRING },
      sortKey: { name: "SK", type: AttributeType.STRING },
      billing: Billing.onDemand(),
      timeToLiveAttribute: "ttl",
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // ---- the service -------------------------------------------------------------

    // Public subnets and no NAT gateway: the tasks reach ECR, S3, DynamoDB and
    // Bedrock directly, and nothing reaches them but the load balancer.
    const vpc = new Vpc(this, "Vpc", {
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [{ name: "public", subnetType: SubnetType.PUBLIC }],
    });
    const cluster = new Cluster(this, "Cluster", { vpc, containerInsightsV2: ContainerInsights.ENABLED });

    const logs = new LogGroup(this, "ServiceLogs", {
      retention: RetentionDays.ONE_MONTH,
      removalPolicy: RemovalPolicy.DESTROY,
    });
    const task = new FargateTaskDefinition(this, "Task", {
      cpu: 1024,
      memoryLimitMiB: 2048,
      runtimePlatform: {
        cpuArchitecture: CpuArchitecture.ARM64,
        operatingSystemFamily: OperatingSystemFamily.LINUX,
      },
    });
    task.addContainer("perception", {
      image:
        props.image ??
        ContainerImage.fromAsset(props.root, {
          file: "services/perception/Dockerfile",
          platform: Platform.LINUX_ARM64,
        }),
      portMappings: [{ containerPort: SERVICE_PORT }],
      logging: LogDrivers.awsLogs({ logGroup: logs, streamPrefix: "perception" }),
      environment: {
        SMC_WORKSPACE: CONTAINER_WORKSPACE,
        SMC_WORKSPACE_S3: workspace.s3UrlForObject(WORKSPACE_PREFIX),
        SMC_SESSIONS_TABLE: sessions.tableName,
        SMC_READ_ONLY: "true",
        // No .env in the image: every setting comes from here.
        SMC_ENV_FILE: "",
        SMC_BEDROCK_REGION: this.region,
        SMC_AGENT_MODEL: props.model,
        SMC_AGENT_EFFORT: "low",
        SMC_AWS_AUTH: "role",
        // The public demo's model calls are capped: past the cap the agent uses the policy's words.
        SMC_MODEL_CALLS_PER_DAY: String(props.modelCallsPerDay),
      },
    });
    workspace.grantRead(task.taskRole, `${WORKSPACE_PREFIX}/*`);
    sessions.grantReadWriteData(task.taskRole);
    task.taskRole.addToPrincipalPolicy(
      new PolicyStatement({
        actions: ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
        // A cross-region profile runs the model in any region it spans.
        resources: [
          `arn:aws:bedrock:${this.region}:${this.account}:inference-profile/${props.model}`,
          `arn:aws:bedrock:*::foundation-model/${props.model.replace(/^[a-z]+\./, "")}`,
        ],
      }),
    );

    const balancerGroup = new SecurityGroup(this, "BalancerGroup", { vpc, allowAllOutbound: true });
    const serviceGroup = new SecurityGroup(this, "ServiceGroup", { vpc, allowAllOutbound: true });
    serviceGroup.addIngressRule(balancerGroup, Port.tcp(SERVICE_PORT), "from the load balancer only");
    const service = new FargateService(this, "Service", {
      cluster,
      taskDefinition: task,
      desiredCount: 1,
      assignPublicIp: true,
      vpcSubnets: { subnetType: SubnetType.PUBLIC },
      securityGroups: [serviceGroup],
      minHealthyPercent: 0,
      maxHealthyPercent: 200,
      circuitBreaker: { rollback: true },
    });

    // Internal: reachable from the VPC link, never from the internet.
    const balancer = new ApplicationLoadBalancer(this, "Balancer", {
      vpc,
      internetFacing: false,
      securityGroup: balancerGroup,
      vpcSubnets: { subnetType: SubnetType.PUBLIC },
    });
    const listener = balancer.addListener("Http", { port: 80, protocol: ApplicationProtocol.HTTP, open: false });
    listener.addTargets("Perception", {
      port: SERVICE_PORT,
      protocol: ApplicationProtocol.HTTP,
      targets: [service],
      healthCheck: { path: "/health", healthyHttpCodes: "200" },
      deregistrationDelay: Duration.seconds(10),
    });

    // ---- the API -------------------------------------------------------------------

    const linkGroup = new SecurityGroup(this, "VpcLinkGroup", { vpc, allowAllOutbound: true });
    // EC2 takes letters, digits and a few signs in a rule's description: no apostrophe.
    balancerGroup.addIngressRule(linkGroup, Port.tcp(80), "from the API Gateway VPC link");
    const link = new VpcLink(this, "VpcLink", {
      vpc,
      subnets: { subnetType: SubnetType.PUBLIC },
      securityGroups: [linkGroup],
    });
    const api = new HttpApi(this, "Api", {
      description: "Spatial Maintenance Copilot: the perception service",
      createDefaultStage: false,
    });
    // A visitor's camera sends a few frames a second; the limit keeps a runaway client off the bill.
    new HttpStage(this, "ApiStage", {
      httpApi: api,
      stageName: "$default",
      autoDeploy: true,
      throttle: { rateLimit: 20, burstLimit: 40 },
    });
    api.addRoutes({
      path: "/api/{proxy+}",
      methods: [HttpMethod.ANY],
      integration: new HttpAlbIntegration("Service", listener, {
        vpcLink: link,
        // /api/localise reaches the service as /localise.
        parameterMapping: new ParameterMapping().overwritePath(MappingValue.custom("/$request.path.proxy")),
      }),
    });

    // ---- the web app -----------------------------------------------------------------

    const site = new Bucket(this, "Site", {
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
      encryption: BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });
    const distribution = new Distribution(this, "Web", {
      comment: "Spatial Maintenance Copilot",
      defaultRootObject: "index.html",
      defaultBehavior: {
        origin: S3BucketOrigin.withOriginAccessControl(site),
        viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        functionAssociations: [
          {
            eventType: FunctionEventType.VIEWER_REQUEST,
            function: new CloudFrontFunction(this, "IndexRewrite", { code: FunctionCode.fromInline(INDEX_REWRITE) }),
          },
        ],
      },
      additionalBehaviors: {
        "/api/*": {
          origin: new HttpOrigin(`${api.apiId}.execute-api.${this.region}.amazonaws.com`),
          viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          allowedMethods: AllowedMethods.ALLOW_ALL,
          cachePolicy: CachePolicy.CACHING_DISABLED,
          originRequestPolicy: OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
        },
      },
      errorResponses: [{ httpStatus: 404, responsePagePath: "/404.html", responseHttpStatus: 404 }],
    });
    const out = join(props.root, "apps", "web", "out");
    if (existsSync(out)) {
      new BucketDeployment(this, "SiteFiles", {
        sources: [Source.asset(out)],
        destinationBucket: site,
        distribution,
      });
    }
    // The service answers only the page's own origin.
    task.defaultContainer?.addEnvironment("CORS_ALLOWED_ORIGINS", `https://${distribution.distributionDomainName}`);

    // ---- observability ---------------------------------------------------------------

    const apiMetric = (metricName: string, statistic = "Sum") =>
      new Metric({
        namespace: "AWS/ApiGateway",
        metricName,
        dimensionsMap: { ApiId: api.apiId },
        statistic,
        period: Duration.minutes(1),
      });
    new Dashboard(this, "Dashboard", {
      dashboardName: `${id}-overview`,
      widgets: [
        [
          new GraphWidget({ title: "Requests", left: [apiMetric("Count")] }),
          new GraphWidget({ title: "Errors", left: [apiMetric("4xx"), apiMetric("5xx")] }),
          new GraphWidget({ title: "Latency (ms)", left: [apiMetric("Latency", "p90"), apiMetric("Latency", "p50")] }),
        ],
        [
          new GraphWidget({ title: "Service CPU (%)", left: [service.metricCpuUtilization()] }),
          new GraphWidget({ title: "Service memory (%)", left: [service.metricMemoryUtilization()] }),
        ],
      ],
    });

    // ---- cost ----------------------------------------------------------------------

    // The account's monthly cost, told by email before it runs over: a public demo is called by anyone.
    if (props.budget) {
      const subscribers = [{ subscriptionType: "EMAIL", address: props.budget.email }];
      new CfnBudget(this, "CostBudget", {
        budget: {
          budgetName: `${id}-monthly`,
          budgetType: "COST",
          timeUnit: "MONTHLY",
          budgetLimit: { amount: props.budget.usd, unit: "USD" },
        },
        notificationsWithSubscribers: [
          {
            notification: { notificationType: "ACTUAL", comparisonOperator: "GREATER_THAN", threshold: 80, thresholdType: "PERCENTAGE" },
            subscribers,
          },
          {
            notification: { notificationType: "FORECASTED", comparisonOperator: "GREATER_THAN", threshold: 100, thresholdType: "PERCENTAGE" },
            subscribers,
          },
        ],
      });
    }

    new CfnOutput(this, "SiteUrl", { value: `https://${distribution.distributionDomainName}` });
    new CfnOutput(this, "WorkspaceBucket", { value: workspace.bucketName });
    new CfnOutput(this, "SessionsTable", { value: sessions.tableName });
    new CfnOutput(this, "ServiceLogGroup", { value: logs.logGroupName });
  }
}

/** The workspace files the deployment serves: the camera, the rig, the chosen atlases and view sets. */
export function workspaceSources(props: Pick<SmcStackProps, "root" | "atlases" | "viewSets">): { source: ISource; prefix: string }[] {
  const at = (...parts: string[]) => join(props.root, ...parts);
  const sources: { source: ISource; prefix: string }[] = [
    { source: Source.asset(at("calib", "intrinsics")), prefix: "calib/intrinsics" },
    { source: Source.data("rig.yaml", readFileSync(at("calib", "rig.yaml"), "utf8")), prefix: "calib" },
  ];
  for (const atlas of props.atlases) {
    const files = [`${atlas}.json`, `${atlas}.report.json`].filter((file) => existsSync(at("data", "atlas", file)));
    if (!files.includes(`${atlas}.json`)) throw new Error(`no atlas ${atlas} in data/atlas`);
    for (const file of files) {
      sources.push({ source: Source.data(file, readFileSync(at("data", "atlas", file), "utf8")), prefix: "data/atlas" });
    }
  }
  for (const set of props.viewSets) {
    if (!existsSync(at("data", "views", set))) throw new Error(`no view set ${set} in data/views`);
    sources.push({ source: Source.asset(at("data", "views", set)), prefix: `data/views/${set}` });
  }
  return sources;
}
