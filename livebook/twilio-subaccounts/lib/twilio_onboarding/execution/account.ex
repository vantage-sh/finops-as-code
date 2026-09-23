defmodule TwilioOnboarding.Execution.Account do
  @moduledoc "Performs one account's checkpointed creation and recovery steps."

  alias TwilioOnboarding.Core.Identifiers
  alias TwilioOnboarding.Core.Recovery
  alias TwilioOnboarding.Execution.Creation
  alias TwilioOnboarding.Journal

  @safe_reasons ~w(unauthorized forbidden rate_limited rejected name_conflict uncertain invalid_response unavailable)a

  @doc "Executes only the next safe action for an account."
  @spec run(map(), map(), map()) :: {:ok, map(), map()} | {:error, atom()}
  def run(entry, journal, context) do
    record = Map.get(journal.records, entry.sid)

    case Recovery.decide(entry, record, context.integrations) do
      :create -> Creation.run(entry, journal, context)
      {:skip, token} -> result(journal, entry.sid, :skipped, token)
      {:complete, token} -> result(journal, entry.sid, :connected, token)
      {:assign, token} -> assign(journal, %{record | integration_token: token}, context)
      {:attention, reason, token} -> result(journal, entry.sid, :needs_attention, token, reason)
      {:attention, reason} -> result(journal, entry.sid, :needs_attention, token(record), reason)
      {:failed, reason} -> result(journal, entry.sid, :failed, token(record), reason)
    end
  end

  @doc "Checkpoints a known integration before assigning its workspace."
  @spec assign(map(), map(), map()) :: {:ok, map(), map()} | {:error, atom()}
  def assign(journal, record, context) do
    with {:ok, updated} <- save(journal, record, "integration_created") do
      vantage = context.adapters.vantage

      response =
        safe_call(fn -> vantage.assign_workspace(context.credentials, record.integration_token, context.workspace) end)

      finish_assignment(response, updated, record)
    end
  end

  @doc "Stores a new outcome using the journal's strict record allowlist."
  @spec save(map(), map(), String.t()) :: {:ok, map()} | {:error, atom()}
  def save(journal, record, outcome), do: Journal.checkpoint(journal, %{record | outcome: outcome})

  @doc "Constructs a customer-visible result without raw errors or credentials."
  @spec result(map(), String.t(), atom(), String.t() | nil, atom() | nil) :: {:ok, map(), map()}
  def result(journal, sid, status, token, reason \\ nil) do
    {:ok, %{sid: sid, status: status, integration_token: token, reason: reason}, journal}
  end

  @doc "Converts unexpected adapter failures into an uncertain remote outcome."
  @spec safe_call((-> term())) :: term()
  def safe_call(callback) do
    case callback.() do
      :ok -> :ok
      {:ok, value} -> {:ok, value}
      {:error, reason} when reason in @safe_reasons -> {:error, reason}
      _ -> {:error, :uncertain}
    end
  rescue
    _ -> {:error, :uncertain}
  catch
    _, _ -> {:error, :uncertain}
  end

  @doc "Reads an inventory without exposing exceptions or unexpected adapter responses."
  @spec safe_read((-> term())) :: {:ok, [map()]} | {:error, atom()}
  def safe_read(callback) do
    case safe_call(callback) do
      {:ok, values} when is_list(values) -> {:ok, values}
      {:error, reason} -> {:error, reason}
      _ -> {:error, :invalid_response}
    end
  end

  @doc "Looks up the exact account identity after an ambiguous integration creation."
  @spec reconcile(map(), map(), map()) :: {:ok, map(), map()} | {:error, atom()}
  def reconcile(journal, record, context) do
    case safe_read(fn -> context.adapters.vantage.list_integrations(context.credentials) end) do
      {:ok, integrations} -> reconcile_matches(journal, record, integrations)
      _ -> result(journal, record.sid, :needs_attention, nil, :outcome_unknown)
    end
  end

  defp finish_assignment(:ok, journal, record) do
    with {:ok, completed} <- save(journal, record, "complete") do
      result(completed, record.sid, :connected, record.integration_token)
    end
  end

  defp finish_assignment({:error, reason}, journal, record) do
    result(journal, record.sid, :workspace_pending, record.integration_token, reason)
  end

  defp finish_assignment(_, journal, record) do
    result(journal, record.sid, :workspace_pending, record.integration_token, :uncertain)
  end

  defp reconcile_matches(journal, record, integrations) do
    case Enum.filter(integrations, &(&1.account_sid == record.sid)) do
      [integration] -> record_match(journal, record, integration)
      _ -> result(journal, record.sid, :needs_attention, nil, :outcome_unknown)
    end
  end

  defp record_match(journal, record, integration) do
    with true <- Identifiers.integration_token?(integration.token),
         found = %{record | integration_token: integration.token},
         {:ok, updated} <- save(journal, found, "integration_unknown") do
      result(updated, record.sid, :needs_attention, integration.token, :integration_found_needs_review)
    else
      false -> result(journal, record.sid, :needs_attention, nil, :outcome_unknown)
      error -> error
    end
  end

  defp token(nil), do: nil
  defp token(record), do: record.integration_token
end
