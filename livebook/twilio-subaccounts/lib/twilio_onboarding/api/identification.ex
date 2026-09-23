defmodule TwilioOnboarding.API.Identification do
  @moduledoc "Confirms a customer-supplied integration identity through a read-only Twilio request."

  alias TwilioOnboarding.API.Twilio
  alias TwilioOnboarding.Core.Identifiers
  alias TwilioOnboarding.Core.Identity
  alias TwilioOnboarding.Core.Inventory
  alias TwilioOnboarding.Credentials

  @doc "Verifies an exact SID before associating its Twilio relationship with an existing integration."
  @spec confirm(Credentials.t(), [Inventory.integration()], String.t(), String.t()) ::
          {:ok, Identity.evidence()} | {:error, atom()}
  def confirm(credentials, integrations, token, sid) do
    with :ok <- integration(integrations, token),
         {:ok, account} <- Twilio.get_account(credentials, sid) do
      Identity.confirm(integrations, token, account)
    end
  end

  defp integration(integrations, token) do
    if Identifiers.integration_token?(token) and Enum.count(integrations, &match?(%{token: ^token}, &1)) == 1 do
      :ok
    else
      {:error, :invalid_integration}
    end
  end
end
