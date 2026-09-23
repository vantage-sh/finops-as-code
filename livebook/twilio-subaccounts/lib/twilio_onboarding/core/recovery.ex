defmodule TwilioOnboarding.Core.Recovery do
  @moduledoc "Decides whether a saved account can proceed without repeating a remote creation."

  @type decision ::
          :create
          | {:skip | :complete | :assign, String.t()}
          | {:attention | :failed, atom()}
          | {:attention, atom(), String.t()}

  @doc "Reconciles one account against the current integration inventory."
  @spec decide(map(), map() | nil, [map()]) :: decision()
  def decide(entry, record, integrations) do
    matches = Enum.filter(integrations, &(&1.account_sid == entry.sid))

    case matches do
      [_, _ | _] -> {:attention, :multiple_integrations}
      _ -> decide_record(record, matches, integrations)
    end
  end

  defp decide_record(nil, [integration], _integrations), do: {:skip, integration.token}

  defp decide_record(nil, [], integrations) do
    if Enum.any?(integrations, &is_nil(&1.account_sid)) do
      {:attention, :unidentified_integrations}
    else
      :create
    end
  end

  defp decide_record(%{outcome: "complete", integration_token: token}, [%{token: token}], _) do
    {:complete, token}
  end

  defp decide_record(%{outcome: outcome}, [integration], _)
       when outcome in ["integration_pending", "integration_unknown"] do
    {:attention, :integration_found_needs_review, integration.token}
  end

  defp decide_record(%{outcome: "integration_created", integration_token: token}, [%{token: token}], _) do
    {:assign, token}
  end

  defp decide_record(%{outcome: "rejected"}, _, _), do: {:failed, :rejected}
  defp decide_record(%{outcome: "cleanup_failed"}, _, _), do: {:attention, :cleanup_failed}
  defp decide_record(%{outcome: "cleanup_pending"}, _, _), do: {:attention, :cleanup_pending}
  defp decide_record(%{outcome: "complete"}, _, _), do: {:attention, :integration_missing}
  defp decide_record(%{outcome: "integration_created"}, _, _), do: {:attention, :integration_missing}
  defp decide_record(_, _, _), do: {:attention, :outcome_unknown}
end
