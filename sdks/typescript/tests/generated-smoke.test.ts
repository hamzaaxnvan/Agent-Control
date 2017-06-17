import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { eventQueryRequestToJSON } from "../src/generated/models/event-query-request";
import { stepToJSON } from "../src/generated/models/step";

describe("generated client layout", () => {
  it("has a generated index entrypoint", () => {
    const generatedIndex = path.resolve(process.cwd(), "src/generated/index.ts");
    expect(existsSync(generatedIndex)).toBe(true);
  });

