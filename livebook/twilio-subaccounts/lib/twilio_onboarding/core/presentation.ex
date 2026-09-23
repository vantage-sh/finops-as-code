defmodule TwilioOnboarding.Core.Presentation do
  @moduledoc "Projects notebook state into a secret-free browser payload."

  alias TwilioOnboarding.Core.Errors
  alias TwilioOnboarding.Core.Plan

  @doc "Return the initial idle display."
  @spec initial() :: map()
  def initial do
    %{
      phase: "ready",
      message: "",
      parent_sid: nil,
      accounts: [],
      workspaces: [],
      integrations: [],
      identification_id: nil,
      identity_blocker: false,
      entries: [],
      results: [],
      review_id: nil,
      workspace: nil
    }
  end

  @doc "Present only eligible account metadata and destination names."
  @spec inventory(map(), String.t(), map(), String.t() | nil) :: map()
  def inventory(inventory, parent_sid, identities \\ %{}, identification_id \\ nil) do
    existing = Map.new(inventory.integrations, &{&1.account_sid, &1.token})
    accounts = inventory.accounts |> Enum.reject(&(&1.sid == parent_sid)) |> Enum.map(&account(&1, parent_sid, existing))
    integrations = Enum.map(inventory.integrations, &integration(&1, parent_sid, identities))
    reason = identity_blocker(integrations, parent_sid)
    unknown = Enum.any?(integrations, &is_nil(&1.account_sid))

    Map.merge(initial(), %{
      phase: if(unknown or not is_nil(reason), do: "identification", else: "selection"),
      parent_sid: parent_sid,
      accounts: accounts,
      workspaces: inventory.workspaces,
      integrations: integrations,
      identification_id: identification_id,
      identity_blocker: not is_nil(reason),
      message: if(is_nil(reason), do: "", else: Errors.message(reason))
    })
  end

  @doc "Show the exact frozen plan and a one-use review identifier."
  @spec review(map(), Plan.t(), String.t()) :: map()
  def review(view, plan, review_id) do
    workspace = Enum.find(view.workspaces, &(&1.token == plan.workspace_token))
    Map.merge(view, %{phase: "review", entries: plan.entries, workspace: workspace, review_id: review_id, message: ""})
  end

  @doc "Append one allowlisted result to the visible progress."
  @spec progress(map(), map()) :: map()
  def progress(view, result), do: %{view | results: view.results ++ [result_row(result)]}

  @doc "Present final connection outcomes separately from import completion."
  @spec finished(map(), [map()]) :: map()
  def finished(view, results), do: %{view | phase: "finished", results: Enum.map(results, &result_row/1), review_id: nil}

  defp account(account, parent_sid, existing) do
    %{
      sid: account.sid,
      name: account.name,
      status: account.status,
      eligible: account.parent_sid == parent_sid and account.status == "active",
      existing: Map.has_key?(existing, account.sid)
    }
  end

  defp integration(integration, parent_sid, identities) do
    evidence = Map.get(identities, integration.token, %{})

    %{
      token: integration.token,
      label: Map.get(integration, :identity_label),
      status: integration.status,
      identity_hint: Map.get(integration, :identity_hint),
      account_sid: integration.account_sid,
      relationship: relationship(integration.account_sid, Map.get(evidence, :parent_sid), parent_sid),
      source: source(integration.account_sid, Map.get(evidence, :source))
    }
  end

  defp relationship(nil, _, _), do: nil
  defp relationship(sid, _, sid), do: "This parent account (overlaps subaccounts)"
  defp relationship(_, parent, parent), do: "Child of this parent account"
  defp relationship(sid, sid, _), do: "Different parent account"
  defp relationship(_, _, _), do: "Different account hierarchy"

  defp source(nil, _), do: nil
  defp source(_, :confirmed), do: "Confirmed for this session"
  defp source(_, :created), do: "Created by this notebook"
  defp source(_, _), do: nil

  defp identity_blocker(integrations, parent_sid) do
    sids = integrations |> Enum.map(& &1.account_sid) |> Enum.reject(&is_nil/1)

    cond do
      parent_sid in sids -> :parent_already_connected
      length(Enum.uniq(sids)) != length(sids) -> :duplicate_integrations
      true -> nil
    end
  end

  defp result_row(result) do
    reason = result[:reason]

    %{
      sid: result.sid,
      status: status(result.status),
      integration_token: result[:integration_token],
      message: if(is_nil(reason), do: "", else: Errors.message(reason))
    }
  end

  defp status(:connected), do: "Connected; importing costs"
  defp status(:skipped), do: "Already connected"
  defp status(:workspace_pending), do: "Connected; workspace needs attention"
  defp status(:failed), do: "Failed; review before retrying"
  defp status(_status), do: "Needs attention"
end
