defmodule TwilioOnboarding.Execution.Creation do
  @moduledoc "Creates account credentials only after persisting each remote write's intent."

  alias TwilioOnboarding.Core.Identifiers
  alias TwilioOnboarding.Execution.Account

  @definitive_rejections ~w(unauthorized forbidden rate_limited rejected name_conflict)a

  @doc "Creates one key and integration, retaining ambiguous outcomes for review."
  @spec run(map(), map(), map()) :: {:ok, map(), map()} | {:error, atom()}
  def run(entry, journal, context) do
    record = %{sid: entry.sid, run_id: context.run_id, key_sid: nil, integration_token: nil, outcome: "key_pending"}

    with {:ok, pending} <- Account.save(journal, record, "key_pending") do
      response =
        Account.safe_call(fn -> context.adapters.twilio.create_key(context.credentials, entry.sid, context.run_id) end)

      handle_key(response, entry, pending, record, context)
    end
  end

  defp handle_key({:ok, %{sid: sid, secret: secret} = key}, entry, journal, record, context) do
    if Identifiers.key_sid?(sid) and is_binary(secret) and byte_size(secret) > 0 do
      create_integration(entry, key, journal, %{record | key_sid: sid}, context)
    else
      unknown_key(journal, record)
    end
  end

  defp handle_key({:error, reason}, _entry, journal, record, _context) when reason in @definitive_rejections do
    with {:ok, updated} <- Account.save(journal, record, "rejected") do
      Account.result(updated, record.sid, :failed, nil, reason)
    end
  end

  defp handle_key(_, _, journal, record, _), do: unknown_key(journal, record)

  defp unknown_key(journal, record) do
    with {:ok, updated} <- Account.save(journal, record, "key_unknown") do
      Account.result(updated, record.sid, :needs_attention, nil, :outcome_unknown)
    end
  end

  defp create_integration(entry, key, journal, record, context) do
    with {:ok, created} <- Account.save(journal, record, "key_created"),
         {:ok, pending} <- Account.save(created, record, "integration_pending") do
      vantage = context.adapters.vantage
      response = Account.safe_call(fn -> vantage.create_integration(context.credentials, entry, key) end)
      handle_integration(response, pending, record, context)
    end
  end

  defp handle_integration({:ok, %{token: token, account_sid: sid}}, journal, record, context) do
    if Identifiers.integration_token?(token) and sid == record.sid do
      Account.assign(journal, %{record | integration_token: token}, context)
    else
      unknown_integration(journal, record, context)
    end
  end

  defp handle_integration({:error, reason}, journal, record, context) when reason in @definitive_rejections do
    with {:ok, pending} <- Account.save(journal, record, "cleanup_pending") do
      cleanup(pending, record, reason, context)
    end
  end

  defp handle_integration(_, journal, record, context), do: unknown_integration(journal, record, context)

  defp unknown_integration(journal, record, context) do
    with {:ok, updated} <- Account.save(journal, record, "integration_unknown") do
      Account.reconcile(updated, record, context)
    end
  end

  defp cleanup(journal, record, reason, context) do
    case Account.safe_call(fn -> context.adapters.twilio.delete_key(context.credentials, record.sid, record.key_sid) end) do
      :ok ->
        with {:ok, updated} <- Account.save(journal, record, "rejected") do
          Account.result(updated, record.sid, :failed, nil, reason)
        end

      _ ->
        with {:ok, updated} <- Account.save(journal, record, "cleanup_failed") do
          Account.result(updated, record.sid, :needs_attention, nil, :cleanup_failed)
        end
    end
  end
end
