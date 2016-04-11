import { AgentControlClient, type ControlDefinitionInput } from "agent-control";

const serverUrl = process.env.AGENT_CONTROL_URL ?? "http://localhost:8000";
// This example creates, updates, and deletes controls, so use an admin key when auth is enabled.
const apiKey = process.env.AGENT_CONTROL_API_KEY;
const controlName = `ts-sdk-example-${Date.now()}`;

const client = new AgentControlClient();
client.init({
  agentName: "typescript-sdk-example",
  serverUrl,
  ...(apiKey ? { apiKey } : {}),
});

async function main(): Promise<void> {
  console.log(`Using server: ${serverUrl}`);

  const health = await client.system.healthCheck();
  console.log(`Health check: ${health.status} (${health.version})`);

  const existing = await client.controls.list({
    limit: 10,
    name: "ts-sdk-example-",
  });
  console.log(`Existing example controls: ${existing.controls.length}`);

  let createdControlId: number | null = null;
  try {
    const created = await client.controls.create({
      name: controlName,
    });
    createdControlId = created.controlId;
    console.log(`Created control: ${controlName} (id=${createdControlId})`);

    const controlData: ControlDefinitionInput = {
      action: { decision: "deny" },
      description: "Block SSN-like patterns in post-step output.",
      enabled: true,
      evaluator: {
        name: "regex",
