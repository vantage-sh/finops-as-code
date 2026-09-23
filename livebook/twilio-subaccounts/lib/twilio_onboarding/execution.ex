defmodule TwilioOnboarding.Execution do
  @moduledoc "Revalidates a reviewed plan and executes it under an exclusive local recovery lock."

  alias TwilioOnboarding.API
  alias TwilioOnboarding.Core.Plan
  alias TwilioOnboarding.Credentials
  alias TwilioOnboarding.Execution.Account
  alias TwilioOnboarding.Execution.Preflight
  alias TwilioOnboarding.Journal

  @doc "Connects reviewed accounts serially, reporting only secret-free results."
  @spec run(Plan.t(), Credentials.t(), (map() -> term())) :: {:ok, [map()]} | {:error, atom()}
  def run(plan, credentials, progress), do: run(plan, credentials, progress, [])

  @doc "Runs with explicit adapters and local storage, allowing isolated offline verification."
  @spec run(Plan.t(), Credentials.t(), (map() -> term()), keyword()) :: {:ok, [map()]} | {:error, atom()}
  def run(
        %{parent_sid: parent, workspace_token: workspace, entries: [_ | _] = entries} = plan,
        %Credentials{} = credentials,
        progress,
        options
      )
      when is_binary(parent) and is_binary(workspace) and is_list(entries) and is_function(progress, 1) do
    if parent == credentials.parent_sid do
      context = %{parent_sid: parent, workspace_token: workspace, fingerprint: Credentials.fingerprint(credentials)}

      adapters = %{
        twilio: Keyword.get(options, :twilio, API.Twilio),
        vantage: Keyword.get(options, :vantage, API.Vantage)
      }

      Journal.with_lock(context, options, &execute(plan, credentials, &1, adapters, progress))
    else
      {:error, :invalid_destination}
    end
  end

  def run(_, _, _, _), do: {:error, :invalid_plan}

  defp execute(plan, credentials, journal, adapters, progress) do
    run_id = 16 |> :crypto.strong_rand_bytes() |> Base.encode16(case: :lower)

    context = %{
      credentials: credentials,
      integrations: [],
      workspace: plan.workspace_token,
      adapters: adapters,
      run_id: run_id
    }

    plan.entries
    |> Enum.reduce_while({:ok, [], journal}, fn entry, {:ok, results, current} ->
      with {:ok, fresh} <- Preflight.load(plan, credentials, adapters, current),
           {:ok, result, updated} <- Account.run(entry, current, %{context | integrations: fresh}) do
        notify(progress, result)
        {:cont, {:ok, [result | results], updated}}
      else
        {:error, reason} ->
          {:halt, {:error, reason}}
      end
    end)
    |> finish()
  end

  defp notify(progress, result) do
    progress.(result)
  rescue
    _ -> :ok
  catch
    _, _ -> :ok
  end

  defp finish({:ok, results, _journal}), do: {:ok, Enum.reverse(results)}
  defp finish(error), do: error
end
