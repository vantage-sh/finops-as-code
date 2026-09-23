defmodule TwilioOnboarding do
  @moduledoc """
  Local Twilio subaccount onboarding for Vantage.

  Core holds decisions; API holds requests; Execution and Journal preserve progress;
  Notebook presents the reviewed customer flow.
  """

  use Boundary, deps: [Req, Kino, Jason], exports: [Notebook, {Core, []}]
end
