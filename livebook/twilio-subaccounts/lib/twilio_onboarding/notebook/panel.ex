defmodule TwilioOnboarding.Notebook.Panel do
  @moduledoc "Handles explicit discovery, preview, and apply events in a local Livebook session."

  use Kino.JS, assets_path: Path.expand("assets", __DIR__)
  use Kino.JS.Live

  alias Kino.JS.Live
  alias Kino.JS.Live.Context
  alias TwilioOnboarding.API.Discovery
  alias TwilioOnboarding.API.Identification
  alias TwilioOnboarding.Core.Errors
  alias TwilioOnboarding.Core.Identity
  alias TwilioOnboarding.Core.Plan
  alias TwilioOnboarding.Core.Presentation, as: View
  alias TwilioOnboarding.Credentials
  alias TwilioOnboarding.Execution
  alias TwilioOnboarding.Notebook.Worker

  @doc "Create an idle wizard with no credentials in browser state."
  @spec new() :: Live.t()
  def new, do: Live.new(__MODULE__, nil)

  @impl true
  @doc "Initialize public display state and empty private session state."
  @spec init(nil, Context.t()) :: {:ok, Context.t()}
  def init(nil, ctx) do
    {:ok,
     assign(ctx,
       view: View.initial(),
       credentials: nil,
       inventory: nil,
       identities: %{},
       plan: nil,
       operation: nil,
       monitor: nil
     )}
  end

  @impl true
  @doc "Send only allowlisted display state to a connected browser."
  @spec handle_connect(Context.t()) :: {:ok, map(), Context.t()}
  def handle_connect(ctx), do: {:ok, ctx.assigns.view, ctx}

  @impl true
  @doc "Accept only actions permitted by the current wizard phase."
  @spec handle_event(String.t(), map(), Context.t()) :: {:noreply, Context.t()}
  def handle_event("discover", _data, %{assigns: %{operation: nil}} = ctx) do
    ctx = assign(ctx, credentials: nil, inventory: nil, identities: %{}, plan: nil)

    start_work(ctx, "discovering", fn ->
      with {:ok, credentials} <- Credentials.from_env(),
           {:ok, inventory} <- Discovery.load(credentials) do
        {:discovered, credentials, inventory}
      end
    end)
  end

  def handle_event(
        "confirm_identity",
        %{"identification_id" => id, "token" => token, "sid" => sid, "confirmed" => true},
        %{assigns: %{operation: nil, view: %{phase: "identification", identification_id: id}}} = ctx
      )
      when is_binary(token) and is_binary(sid) do
    %{credentials: credentials, inventory: inventory} = ctx.assigns

    start_work(ctx, "identifying", fn ->
      case Identification.confirm(credentials, inventory.integrations, token, sid) do
        {:ok, evidence} -> {:identified, token, evidence}
        {:error, reason} -> {:identification_error, reason}
      end
    end)
  end

  def handle_event("review_identities", _data, %{assigns: %{operation: nil, view: %{phase: "selection"}}} = ctx) do
    view = %{ctx.assigns.view | phase: "identification", identification_id: reference(), message: ""}
    ctx |> assign(plan: nil) |> publish(view)
  end

  def handle_event("continue_selection", _data, %{assigns: %{operation: nil, view: %{phase: "identification"}}} = ctx) do
    publish_inventory(ctx)
  end

  def handle_event(
        "preview",
        %{"selected" => selected, "workspace" => workspace},
        %{assigns: %{operation: nil, view: %{phase: "selection"}, inventory: inventory, credentials: credentials}} = ctx
      )
      when is_map(inventory) and is_map(credentials) and is_list(selected) and length(selected) <= 10_000 do
    with true <- Enum.any?(inventory.workspaces, &(&1.token == workspace)),
         {:ok, plan} <-
           Plan.build(credentials.parent_sid, inventory.accounts, inventory.integrations, selected, workspace) do
      plan = Map.put(plan, :identities, ctx.assigns.identities)
      view = View.review(ctx.assigns.view, plan, reference())
      publish(assign(ctx, plan: plan), view)
    else
      false -> show_error(ctx, :invalid_destination)
      {:error, reason} -> show_error(ctx, reason)
    end
  end

  def handle_event(
        "apply",
        %{"review_id" => id, "confirmed" => true},
        %{assigns: %{operation: nil, view: %{phase: "review", review_id: id}, plan: plan, credentials: credentials}} = ctx
      )
      when is_map(plan) and is_struct(credentials, Credentials) do
    owner = self()
    progress = fn result -> send(owner, {:progress, result}) end

    start_work(assign(ctx, plan: nil, credentials: nil), "connecting", fn ->
      Execution.run(plan, credentials, progress)
    end)
  end

  def handle_event("clear", _data, %{assigns: %{operation: nil}} = ctx) do
    ctx |> assign(credentials: nil, inventory: nil, identities: %{}, plan: nil) |> publish(View.initial())
  end

  def handle_event(_event, _data, ctx), do: {:noreply, ctx}

  @impl true
  @doc "Render safe progress and completed work without exposing worker arguments."
  @spec handle_info(term(), Context.t()) :: {:noreply, Context.t()}
  def handle_info({:finished, reference, result}, %{assigns: %{operation: reference}} = ctx) do
    Process.demonitor(ctx.assigns.monitor, [:flush])
    finish(result, assign(ctx, operation: nil, monitor: nil))
  end

  def handle_info({:progress, result}, %{assigns: %{view: %{phase: "connecting"}}} = ctx) do
    publish(ctx, View.progress(ctx.assigns.view, result))
  end

  def handle_info({:DOWN, monitor, :process, _pid, _reason}, %{assigns: %{monitor: monitor}} = ctx) do
    ctx |> assign(operation: nil, monitor: nil) |> show_error(:outcome_unknown)
  end

  def handle_info(_message, ctx), do: {:noreply, ctx}

  defp start_work(ctx, phase, operation) do
    owner = self()
    reference = make_ref()
    {_pid, monitor} = Worker.start(owner, reference, operation)
    view = Map.merge(ctx.assigns.view, %{phase: phase, message: "", results: [], review_id: nil})
    ctx |> assign(operation: reference, monitor: monitor) |> publish(view)
  end

  defp finish({:discovered, credentials, inventory}, ctx) do
    identities = Map.get(inventory, :identities, %{})

    ctx
    |> assign(credentials: credentials, inventory: inventory, identities: identities, plan: nil)
    |> publish_inventory()
  end

  defp finish({:identified, token, evidence}, ctx) do
    identities = Map.put(ctx.assigns.identities, token, evidence)
    ctx |> assign(identities: identities, plan: nil) |> publish_inventory()
  end

  defp finish({:identification_error, reason}, ctx), do: identification_error(ctx, reason)
  defp finish({:ok, results}, ctx), do: publish(ctx, View.finished(ctx.assigns.view, results))
  defp finish({:error, reason}, ctx), do: show_error(ctx, reason)

  defp publish_inventory(ctx) do
    %{inventory: inventory, identities: identities, credentials: credentials} = ctx.assigns
    resolved = %{inventory | integrations: Identity.resolve(inventory.integrations, identities)}
    view = View.inventory(resolved, credentials.parent_sid, identities, reference())
    ctx |> assign(inventory: resolved) |> publish(view)
  end

  defp identification_error(ctx, reason) do
    view = %{ctx.assigns.view | phase: "identification", message: Errors.identification_message(reason)}
    publish(ctx, view)
  end

  defp show_error(%{assigns: %{view: %{phase: "identifying"}}} = ctx, reason), do: identification_error(ctx, reason)

  defp show_error(ctx, reason) do
    view = error_view(ctx.assigns.view, reason)
    ctx |> assign(plan: nil, credentials: nil, inventory: nil, identities: %{}) |> publish(view)
  end

  defp error_view(%{phase: "discovering"}, reason) when reason in [:missing_credentials, :invalid_credentials],
    do: Map.put(View.initial(), :message, Errors.validation_message(reason))

  defp error_view(%{phase: "discovering"} = view, reason),
    do: %{view | phase: "attention", message: Errors.validation_message(reason), review_id: nil}

  defp error_view(view, reason), do: %{view | phase: "attention", message: Errors.message(reason), review_id: nil}

  defp publish(ctx, view) do
    broadcast_event(ctx, "state", view)
    {:noreply, assign(ctx, view: view)}
  end

  defp reference, do: 16 |> :crypto.strong_rand_bytes() |> Base.encode16(case: :lower)
end
