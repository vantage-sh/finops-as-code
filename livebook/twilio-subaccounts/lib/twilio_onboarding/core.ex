defmodule TwilioOnboarding.Core do
  @moduledoc "Pure identity, inventory, planning, payload, and recovery decisions."

  use Boundary,
    type: :strict,
    deps: [],
    exports: [Identifiers, Inventory, Identity, Plan, Payloads, Errors, Recovery, Presentation, Storage]
end
