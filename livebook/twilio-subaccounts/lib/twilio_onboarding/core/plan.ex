defmodule TwilioOnboarding.Core.Plan do
  @moduledoc "Builds a deterministic, reviewed plan without performing remote operations."

  alias TwilioOnboarding.Core.Identifiers
  alias TwilioOnboarding.Core.Inventory

  @type entry :: %{
          sid: String.t(),
          name: String.t(),
          action: :connect | :skip,
          integration_token: String.t() | nil
        }
  @type t :: %{
          required(:parent_sid) => String.t(),
          required(:workspace_token) => String.t(),
          required(:entries) => [entry()],
          optional(:identities) => map()
        }

  @doc "Plans only selected active children, blocking ambiguous identity and overlapping costs."
  @spec build(String.t(), [Inventory.account()], [Inventory.integration()], [String.t()], String.t()) ::
          {:ok, t()} | {:error, atom()}
  def build(parent_sid, accounts, integrations, selected_sids, workspace_token)
      when is_list(accounts) and is_list(integrations) and is_list(selected_sids) do
    with :ok <- validate_identifiers(parent_sid, workspace_token),
         :ok <- validate_inventory(accounts, integrations),
         :ok <- validate_integrations(parent_sid, integrations),
         :ok <- validate_selection(parent_sid, accounts, selected_sids) do
      selected = accounts |> Enum.filter(&(&1.sid in selected_sids)) |> Enum.sort_by(& &1.sid)
      names = names(selected)
      existing = Map.new(integrations, &{&1.account_sid, &1.token})
      entries = Enum.map(selected, &entry(&1, names, existing))
      {:ok, %{parent_sid: parent_sid, workspace_token: workspace_token, entries: entries}}
    end
  end

  def build(_, _, _, _, _), do: {:error, :invalid_inventory}

  defp validate_identifiers(parent_sid, workspace_token) do
    if Identifiers.account_sid?(parent_sid) and Identifiers.workspace_token?(workspace_token) do
      :ok
    else
      {:error, :invalid_destination}
    end
  end

  defp validate_inventory(accounts, integrations) do
    with true <- Enum.all?(accounts, &valid_account?/1),
         true <- Enum.all?(integrations, &valid_integration?/1),
         true <- unique?(Enum.map(accounts, & &1.sid)),
         true <- unique?(Enum.map(integrations, & &1.token)) do
      :ok
    else
      _ -> {:error, :invalid_inventory}
    end
  end

  defp valid_account?(%{sid: sid, parent_sid: parent, name: name, status: status}) do
    match?(
      {:ok, %{name: ^name}},
      Inventory.account(%{
        "sid" => sid,
        "owner_account_sid" => parent,
        "friendly_name" => name,
        "status" => status
      })
    )
  end

  defp valid_account?(_), do: false

  defp valid_integration?(%{token: token, account_sid: sid, status: status}) do
    (is_nil(sid) or Identifiers.account_sid?(sid)) and
      match?({:ok, _}, Inventory.integration(%{"token" => token, "status" => status}))
  end

  defp valid_integration?(_), do: false

  defp validate_integrations(parent_sid, integrations) do
    sids = Enum.map(integrations, & &1.account_sid)

    cond do
      nil in sids -> {:error, :unidentified_integration}
      parent_sid in sids -> {:error, :parent_already_connected}
      not unique?(sids) -> {:error, :duplicate_integrations}
      true -> :ok
    end
  end

  defp validate_selection(_, _, []), do: {:error, :no_accounts_selected}

  defp validate_selection(parent_sid, accounts, selected_sids) do
    eligible =
      accounts
      |> Enum.filter(&(&1.parent_sid == parent_sid and &1.sid != parent_sid and &1.status == "active"))
      |> Enum.map(& &1.sid)

    cond do
      not unique?(selected_sids) -> {:error, :duplicate_selection}
      not Enum.all?(selected_sids, &(&1 in eligible)) -> {:error, :invalid_selection}
      true -> :ok
    end
  end

  defp names(accounts) do
    frequencies = Enum.frequencies_by(accounts, & &1.name)
    proposed = Map.new(accounts, &{&1.sid, name(&1, frequencies[&1.name])})

    if unique?(Map.values(proposed)) do
      proposed
    else
      Map.new(accounts, &{&1.sid, &1.sid})
    end
  end

  defp name(account, 1), do: account.name
  defp name(account, _), do: String.slice(account.name, 0, 160) <> " (" <> account.sid <> ")"

  defp entry(account, names, existing) do
    case Map.fetch(existing, account.sid) do
      {:ok, token} -> %{sid: account.sid, name: names[account.sid], action: :skip, integration_token: token}
      :error -> %{sid: account.sid, name: names[account.sid], action: :connect, integration_token: nil}
    end
  end

  defp unique?(values), do: length(Enum.uniq(values)) == length(values)
end
