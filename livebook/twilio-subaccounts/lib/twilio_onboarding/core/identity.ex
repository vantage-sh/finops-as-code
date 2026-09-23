defmodule TwilioOnboarding.Core.Identity do
  @moduledoc "Reconciles integration identities using explicit confirmation or successful creation records."

  alias TwilioOnboarding.Core.Identifiers
  alias TwilioOnboarding.Core.Inventory

  @type evidence :: %{
          account_sid: String.t(),
          parent_sid: String.t(),
          source: :confirmed | :created,
          identity_label: String.t() | nil
        }
  @type identities :: %{String.t() => evidence()}

  @doc "Applies evidence only to the same integration and unchanged display label."
  @spec resolve([Inventory.integration()], identities()) :: [Inventory.integration()]
  def resolve(integrations, identities) do
    unique_tokens = unique_tokens(integrations)

    Enum.map(integrations, fn integration ->
      evidence = Map.get(identities, integration.token)

      sid =
        if MapSet.member?(unique_tokens, integration.token) and applicable?(evidence, integration) do
          evidence.account_sid
        end

      Map.put(integration, :account_sid, sid)
    end)
  end

  @doc "Associates a normalized Twilio account with one currently listed integration."
  @spec confirm([Inventory.integration()], String.t(), Inventory.account()) ::
          {:ok, evidence()} | {:error, :invalid_integration | :invalid_response}
  def confirm(integrations, token, account) do
    with {:ok, integration} <- integration(integrations, token),
         {:ok, account} <- account(account) do
      {:ok, evidence(integration, account, :confirmed)}
    end
  end

  @doc "Restores identities from exact successful creation records and the current account inventory."
  @spec from_records(map(), [Inventory.integration()], [Inventory.account()]) :: identities()
  def from_records(records, integrations, accounts) do
    records
    |> Map.values()
    |> Enum.flat_map(&created_identity(&1, integrations, accounts))
    |> Enum.group_by(fn {token, _evidence} -> token end, fn {_token, evidence} -> evidence end)
    |> Enum.flat_map(fn {token, evidence} ->
      case Enum.uniq(evidence) do
        [identity] -> [{token, identity}]
        _ambiguous -> []
      end
    end)
    |> Map.new()
  end

  defp created_identity(%{outcome: outcome, sid: sid, integration_token: token}, integrations, accounts)
       when outcome in ["integration_created", "complete"] do
    with {:ok, integration} <- integration(integrations, token),
         [account] <- Enum.filter(accounts, &match?(%{sid: ^sid}, &1)),
         {:ok, account} <- account(account) do
      [{token, evidence(integration, account, :created)}]
    else
      _ -> []
    end
  end

  defp created_identity(_record, _integrations, _accounts), do: []

  defp integration(integrations, token) do
    with true <- Identifiers.integration_token?(token),
         [integration] <- Enum.filter(integrations, &match?(%{token: ^token}, &1)) do
      {:ok, integration}
    else
      _ -> {:error, :invalid_integration}
    end
  end

  defp account(%{sid: sid, parent_sid: parent, name: name, status: status}) do
    Inventory.account(%{"sid" => sid, "owner_account_sid" => parent, "friendly_name" => name, "status" => status})
  end

  defp account(_), do: {:error, :invalid_response}

  defp evidence(integration, account, source) do
    %{
      account_sid: account.sid,
      parent_sid: account.parent_sid,
      source: source,
      identity_label: Map.get(integration, :identity_label)
    }
  end

  defp applicable?(%{account_sid: sid, parent_sid: parent, source: source, identity_label: label}, integration)
       when source in [:confirmed, :created] do
    Identifiers.integration_token?(integration.token) and Identifiers.account_sid?(sid) and
      Identifiers.account_sid?(parent) and label == Map.get(integration, :identity_label)
  end

  defp applicable?(_, _), do: false

  defp unique_tokens(integrations) do
    integrations
    |> Enum.frequencies_by(& &1.token)
    |> Enum.filter(fn {_token, count} -> count == 1 end)
    |> MapSet.new(fn {token, _count} -> token end)
  end
end
