/**
 * Evaluator Registry
 *
 * This module exports all available evaluators and provides
 * utilities for working with them.
 *
 * ## Adding a New Evaluator
 *
 * 1. Create a new folder under `evaluators/` (e.g., `evaluators/my-evaluator/`)
 * 2. Create the following files:
 *    - `types.ts` - Form value types
 *    - `form.tsx` - React form component
 *    - `index.ts` - Evaluator definition (implements EvaluatorDefinition interface)
 * 3. Import and add the evaluator to the `evaluators` array below
 * 4. That's it! The main edit-control component will automatically pick it up.
 *
 * @example
 * ```typescript
 * // evaluators/my-evaluator/index.ts
 * import type { EvaluatorDefinition } from "../types";
 * import { MyForm } from "./form";
 * import type { MyFormValues } from "./types";
 *
 * export const myEvaluator: EvaluatorDefinition<MyFormValues> = {
 *   id: "my-evaluator",
 *   displayName: "My Evaluator",
 *   initialValues: { ... },
 *   validate: { ... },
 *   toConfig: (values) => ({ ... }),
 *   fromConfig: (config) => ({ ... }),
 *   FormComponent: MyForm,
 * };
 * ```
 */

import {
  defenseClawOpaPolicyEvaluator,
