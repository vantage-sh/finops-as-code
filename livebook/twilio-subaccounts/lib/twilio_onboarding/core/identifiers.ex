defmodule TwilioOnboarding.Core.Identifiers do
  @moduledoc "Validates identifiers before they enter URLs, plans, or recovery records."

  @doc "Checks the Twilio account SID format."
  @spec account_sid?(term()) :: boolean()
  def account_sid?(value), do: matches?(value, ~r/\AAC[0-9a-fA-F]{32}\z/)

  @doc "Checks the Twilio API key SID format."
  @spec key_sid?(term()) :: boolean()
  def key_sid?(value), do: matches?(value, ~r/\ASK[0-9a-fA-F]{32}\z/)

  @doc "Checks a Vantage integration token."
  @spec integration_token?(term()) :: boolean()
  def integration_token?(value), do: matches?(value, ~r/\Aaccss_crdntl_[0-9a-f]{16}\z/)

  @doc "Checks a Vantage workspace token."
  @spec workspace_token?(term()) :: boolean()
  def workspace_token?(value), do: matches?(value, ~r/\Awrkspc_[0-9a-f]{16}\z/)

  defp matches?(value, pattern) when is_binary(value), do: Regex.match?(pattern, value)
  defp matches?(_, _), do: false
end
