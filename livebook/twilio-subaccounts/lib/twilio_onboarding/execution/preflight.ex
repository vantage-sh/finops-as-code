defmodule TwilioOnboarding.Execution.Preflight do
  @moduledoc "Refreshes identity evidence before a reviewed account can change remote state."

  alias TwilioOnboarding.Core.Identifiers
  alias TwilioOnboarding.Core.Identity
  alias TwilioOnboarding.Core.Plan
  alias TwilioOnboarding.Execution.Account

  @doc "Rechecks current inventories, confirmed relationships, and the frozen selection."
  @spec load(map(), map(), map(), map()) :: {:ok, [map()]} | {:error, atom()}
  def load(plan, credentials, adapters, journal) do
    with {:ok, accounts} <- Account.safe_read(fn -> adapters.twilio.list_accounts(credentials) end),
         {:ok, integrations} <- Account.safe_read(fn -> adapters.vantage.list_integrations(credentials) end),
         {:ok, confirmed} <- confirm(plan, credentials, adapters, integrations),
         saved = Identity.from_records(journal.records, integrations, accounts),
         resolved = Identity.resolve(integrations, Map.merge(saved, confirmed)),
         :ok <- revalidate(plan, accounts, resolved) do
      {:ok, resolved}
    end
  end

  defp confirm(plan, credentials, adapters, integrations) do
    plan
    |> Map.get(:identities, %{})
    |> Enum.filter(fn {_token, evidence} -> evidence.source == :confirmed end)
    |> Enum.reduce_while({:ok, %{}}, fn {token, evidence}, {:ok, confirmed} ->
      case confirm_one(credentials, adapters.twilio, integrations, token, evidence) do
        {:ok, verified} -> {:cont, {:ok, Map.put(confirmed, token, verified)}}
        error -> {:halt, error}
      end
    end)
  end

  defp confirm_one(credentials, twilio, integrations, token, evidence) do
    with {:ok, account} <- Account.safe_call(fn -> twilio.get_account(credentials, evidence.account_sid) end),
         {:ok, verified} <- Identity.confirm(integrations, token, account),
         true <- verified == evidence do
      {:ok, verified}
    else
      false -> {:error, :plan_changed}
      error -> error
    end
  end

  defp revalidate(plan, accounts, integrations) do
    with true <- Enum.all?(plan.entries, &valid_entry?/1),
         selected = Enum.map(plan.entries, & &1.sid),
         {:ok, fresh} <- Plan.build(plan.parent_sid, accounts, integrations, selected, plan.workspace_token),
         true <- skips_unchanged?(plan.entries, fresh.entries) do
      :ok
    else
      false -> {:error, :plan_changed}
      error -> error
    end
  end

  defp valid_entry?(%{sid: sid, name: name, action: action, integration_token: token}) do
    Identifiers.account_sid?(sid) and is_binary(name) and byte_size(name) in 1..800 and
      valid_action?(action, token)
  end

  defp valid_entry?(_), do: false
  defp valid_action?(:connect, nil), do: true
  defp valid_action?(:skip, token), do: Identifiers.integration_token?(token)
  defp valid_action?(_, _), do: false

  defp skips_unchanged?(reviewed, fresh) do
    Enum.all?(reviewed, fn
      %{action: :connect} -> true
      entry -> Enum.any?(fresh, &(&1.sid == entry.sid and &1.integration_token == entry.integration_token))
    end)
  end
end
