defmodule TwilioOnboarding.API.Discovery do
  @moduledoc "Read and validate the parent, children, integrations, and Vantage destinations."

  alias TwilioOnboarding.API.Twilio
  alias TwilioOnboarding.API.Vantage
  alias TwilioOnboarding.Core.Identity
  alias TwilioOnboarding.Credentials
  alias TwilioOnboarding.Journal

  @doc "Load complete inventories without creating keys or integrations."
  @spec load(Credentials.t(), keyword()) :: {:ok, map()} | {:error, atom()}
  def load(%Credentials{parent_sid: sid} = credentials, options \\ []) do
    context = %{parent_sid: sid, fingerprint: Credentials.fingerprint(credentials)}

    with {:ok, accounts} <- Twilio.list_accounts(credentials),
         true <- Enum.any?(accounts, &(&1.sid == sid and &1.parent_sid == sid and &1.status == "active")),
         {:ok, integrations} <- Vantage.list_integrations(credentials),
         {:ok, workspaces} <- Vantage.list_workspaces(credentials),
         false <- workspaces == [],
         {:ok, records} <- Journal.records(context, options) do
      identities = Identity.from_records(records, integrations, accounts)

      {:ok,
       %{
         accounts: accounts,
         integrations: Identity.resolve(integrations, identities),
         identities: identities,
         workspaces: workspaces
       }}
    else
      true -> {:error, :no_workspaces}
      false -> {:error, :invalid_parent}
      {:error, reason} -> {:error, reason}
    end
  end
end
