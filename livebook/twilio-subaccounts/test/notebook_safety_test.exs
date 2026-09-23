defmodule TwilioOnboarding.NotebookSafetyTest do
  use ExUnit.Case, async: true

  import Kino.Test

  alias Kino.JS.Live.Context
  alias TwilioOnboarding.Core.Presentation
  alias TwilioOnboarding.Credentials
  alias TwilioOnboarding.Notebook.Panel
  alias TwilioOnboarding.Notebook.Worker

  setup :configure_livebook_bridge

  test "opening the panel creates no worker and exposes no credentials" do
    panel = Panel.new()
    assert panel.export == false
    assert connect(panel) == Presentation.initial()
    push_event(panel, "apply", %{"confirmed" => true, "review_id" => "forged"})
    assert connect(panel) == Presentation.initial()
  end

  test "stale preview cannot rebuild a review after refresh fails" do
    {:ok, credentials} =
      Credentials.new("AC" <> String.duplicate("1", 32), String.duplicate("x", 32), String.duplicate("y", 32))

    state = %{operation: nil, view: %{phase: "attention"}, inventory: %{workspaces: []}, credentials: credentials}
    ctx = %Context{assigns: state}
    assert {:noreply, ^ctx} = Panel.handle_event("preview", %{"selected" => [], "workspace" => "stale"}, ctx)
  end

  test "result display excludes unexpected secret fields" do
    result = %{
      sid: "AC" <> String.duplicate("1", 32),
      status: :connected,
      integration_token: nil,
      reason: nil,
      secret: "canary-do-not-export"
    }

    rendered = Presentation.finished(Presentation.initial(), [result])
    refute inspect(rendered) =~ "canary-do-not-export"
    assert hd(rendered.results).status == "Connected; importing costs"
  end

  test "worker exceptions return only a fixed error without logging secrets" do
    reference = make_ref()
    {_pid, monitor} = Worker.start(self(), reference, fn -> raise "canary-do-not-log" end)
    assert_receive {:finished, ^reference, {:error, :outcome_unknown}}
    assert_receive {:DOWN, ^monitor, :process, _pid, :normal}
  end

  test "closing a panel normally cancels its worker" do
    observer = self()

    owner =
      spawn(fn ->
        {worker, _monitor} =
          Worker.start(self(), make_ref(), fn ->
            send(observer, {:worker_started, self()})

            receive do
              :continue -> send(observer, :unexpected_write)
            end
          end)

        send(observer, {:worker, worker})

        receive do
          :close -> :ok
        end
      end)

    assert_receive {:worker, worker}
    assert_receive {:worker_started, ^worker}
    monitor = Process.monitor(worker)
    send(owner, :close)
    assert_receive {:DOWN, ^monitor, :process, ^worker, :killed}
    send(worker, :continue)
    refute_received :unexpected_write
  end

  test "a dead panel prevents a worker from starting" do
    observer = self()
    owner = spawn(fn -> :ok end)
    owner_monitor = Process.monitor(owner)
    assert_receive {:DOWN, ^owner_monitor, :process, ^owner, _reason}
    {worker, monitor} = Worker.start(owner, make_ref(), fn -> send(observer, :unexpected_write) end)
    assert_receive {:DOWN, ^monitor, :process, ^worker, :killed}
    refute_received :unexpected_write
  end
end
