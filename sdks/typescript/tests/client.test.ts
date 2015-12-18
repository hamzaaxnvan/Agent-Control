import { describe, expect, it } from "vitest";

import { AgentControlClient } from "../src/client";

describe("AgentControlClient", () => {
  it("stores init config", () => {
    const client = new AgentControlClient();

    client.init({
