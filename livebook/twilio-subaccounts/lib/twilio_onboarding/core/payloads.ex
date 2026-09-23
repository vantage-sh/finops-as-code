defmodule TwilioOnboarding.Core.Payloads do
  @moduledoc "Constructs the allowlisted fields sent to Twilio and Vantage."

  alias TwilioOnboarding.Core.Plan

  @doc "Builds the account-specific Standard API key request."
  @spec key(String.t(), String.t()) :: %{String.t() => String.t()}
  def key(account_sid, run_id) do
    %{"AccountSid" => account_sid, "FriendlyName" => "vantage-" <> run_id}
  end

  @doc "Builds an integration request with the child key and an exact rerun identity marker."
  @spec integration(Plan.entry(), %{sid: String.t(), secret: String.t()}) :: %{String.t() => String.t()}
  def integration(%{sid: account_sid, name: name}, %{sid: key_sid, secret: secret}) do
    %{
      "api_key" => key_sid,
      "api_secret" => secret,
      "account_sid" => account_sid,
      "friendly_account_name" => name,
      "description" => "Twilio sub-account " <> account_sid
    }
  end
end
