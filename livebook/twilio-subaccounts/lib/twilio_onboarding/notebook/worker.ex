defmodule TwilioOnboarding.Notebook.Worker do
  @moduledoc "Runs notebook work only while its owning panel remains alive."

  @doc "Start monitored work and cancel it if the panel closes, even with a normal exit."
  @spec start(pid(), reference(), (-> term())) :: {pid(), reference()}
  def start(owner, reference, operation) do
    {worker, monitor} = spawn_monitor(fn -> await_start(owner, reference, operation) end)
    spawn(fn -> guard(owner, worker) end)
    {worker, monitor}
  end

  defp await_start(owner, reference, operation) do
    receive do
      :start -> send(owner, {:finished, reference, safely(operation)})
    end
  end

  defp guard(owner, worker) do
    owner_monitor = Process.monitor(owner)
    worker_monitor = Process.monitor(worker)

    if Process.alive?(owner) do
      send(worker, :start)
    else
      Process.exit(worker, :kill)
    end

    receive do
      {:DOWN, ^owner_monitor, :process, ^owner, _reason} -> Process.exit(worker, :kill)
      {:DOWN, ^worker_monitor, :process, ^worker, _reason} -> :ok
    end
  end

  defp safely(operation) do
    operation.()
  rescue
    _exception -> {:error, :outcome_unknown}
  catch
    _kind, _reason -> {:error, :outcome_unknown}
  end
end
