defmodule TwilioOnboarding.API.Vantage do
  @moduledoc "Vantage integration inventory, creation, and explicit workspace assignment."

  alias TwilioOnboarding.API.HTTP
  alias TwilioOnboarding.API.Pages
  alias TwilioOnboarding.Core.Inventory
  alias TwilioOnboarding.Core.Payloads
  alias TwilioOnboarding.Core.Plan
  alias TwilioOnboarding.Credentials
  alias TwilioOnboarding.Key

  @doc "List every existing Twilio integration visible to the credential."
  @spec list_integrations(Credentials.t()) :: {:ok, [map()]} | {:error, atom()}
  def list_integrations(credentials) do
    Pages.list(
      :vantage,
      credentials,
      "/v2/integrations",
      [provider: "twilio", limit: 1000],
      "integrations",
      &Inventory.integration/1
    )
  end

  @doc "List the available Vantage destinations."
  @spec list_workspaces(Credentials.t()) :: {:ok, [map()]} | {:error, atom()}
  def list_workspaces(credentials) do
    Pages.list(:vantage, credentials, "/v2/workspaces", [limit: 1000], "workspaces", &Inventory.workspace/1)
  end

  @doc "Connect a child's newly created key using the reviewed account name."
  @spec create_integration(Credentials.t(), Plan.entry(), Key.t()) :: {:ok, map()} | {:error, atom()}
  def create_integration(credentials, entry, key) do
    with {:ok, body} <-
           HTTP.call(:vantage, credentials, :post, "/v2/integrations/twilio",
             json: Payloads.integration(entry, Map.take(key, [:sid, :secret]))
           ) do
      case Inventory.integration(body) do
        {:ok, %{identity_hint: sid} = integration} when is_nil(sid) or sid == entry.sid ->
          {:ok, %{integration | account_sid: entry.sid}}

        _other ->
          {:error, :uncertain}
      end
    end
  end

  @doc "Assign only a newly created integration to the selected workspace."
  @spec assign_workspace(Credentials.t(), String.t(), String.t()) :: :ok | {:error, atom()}
  def assign_workspace(credentials, token, workspace_token) do
    if Regex.match?(~r/\Aaccss_crdntl_[0-9a-f]{16}\z/, token) and
         Regex.match?(~r/\Awrkspc_[0-9a-f]{16}\z/, workspace_token) do
      assign(credentials, token, workspace_token)
    else
      {:error, :invalid_response}
    end
  end

  defp assign(credentials, token, workspace_token) do
    case HTTP.call(:vantage, credentials, :put, "/v2/integrations/#{token}", json: %{workspace_tokens: [workspace_token]}) do
      {:ok, _body} -> :ok
      error -> error
    end
  end
end
