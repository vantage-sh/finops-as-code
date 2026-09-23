defmodule TwilioOnboarding.IdentificationFlowTest do
  use ExUnit.Case, async: false

  import Kino.Test

  alias Kino.JS.Live.Context
  alias TwilioOnboarding.Core.Presentation
  alias TwilioOnboarding.Credentials
  alias TwilioOnboarding.Notebook.Panel

  @parent "AC00000000000000000000000000000001"
  @child "AC00000000000000000000000000000002"
  @token "accss_crdntl_0000000000000001"
  @workspace "wrkspc_0000000000000001"

  setup :configure_livebook_bridge

  setup do
    previous = Req.default_options()
    Req.default_options(plug: {Req.Test, __MODULE__})
    Req.Test.set_req_test_to_shared()
    Req.Test.verify_on_exit!()

    on_exit(fn ->
      Req.default_options(previous)
      Req.Test.set_req_test_to_private()
    end)

    :ok
  end

  test "a label hint requires identification and never becomes evidence by itself" do
    ctx = context()
    assert ctx.assigns.view.phase == "identification"
    assert hd(ctx.assigns.view.integrations).identity_hint == @child
    assert hd(ctx.assigns.view.integrations).account_sid == nil
    assert {:noreply, continued} = Panel.handle_event("continue_selection", %{}, ctx)
    assert continued.assigns.view.phase == "identification"
    refute inspect(continued.assigns.view) =~ "private-auth-canary"
  end

  test "an explicit confirmation reads the exact Twilio account and carries evidence into review" do
    expect_account(@child, @parent)
    finished = confirm(context(), @child)
    assert finished.assigns.view.phase == "selection"
    assert hd(finished.assigns.view.integrations).relationship == "Child of this parent account"
    assert hd(finished.assigns.view.integrations).source == "Confirmed for this session"
    assert hd(finished.assigns.view.accounts).existing

    assert {:noreply, reviewed} =
             Panel.handle_event("preview", %{"selected" => [@child], "workspace" => @workspace}, finished)

    assert reviewed.assigns.plan.identities[@token].account_sid == @child
    assert reviewed.assigns.view.phase == "review"
    refute Map.has_key?(reviewed.assigns.view, :identities)
  end

  test "unconfirmed and stale events cannot start an identification request" do
    ctx = context()
    observer = self()

    Req.Test.stub(__MODULE__, fn conn ->
      send(observer, :unexpected_request)
      Plug.Conn.send_resp(conn, 500, "")
    end)

    for payload <- [
          Map.put(payload(ctx, @child), "confirmed", false),
          Map.put(payload(ctx, @child), "identification_id", "stale")
        ] do
      assert {:noreply, ^ctx} = Panel.handle_event("confirm_identity", payload, ctx)
    end

    assert {:noreply, ^ctx} = Panel.handle_event("apply", %{"confirmed" => true, "review_id" => "forged"}, ctx)
    refute_received :unexpected_request
  end

  test "a forged integration token is rejected before contacting Twilio" do
    ctx = context()
    observer = self()

    Req.Test.stub(__MODULE__, fn conn ->
      send(observer, :unexpected_request)
      Plug.Conn.send_resp(conn, 500, "")
    end)

    event = Map.put(payload(ctx, @child), "token", "accss_crdntl_0000000000000099")
    assert {:noreply, working} = Panel.handle_event("confirm_identity", event, ctx)
    finished = finish_worker(working)
    assert finished.assigns.view.phase == "identification"
    assert finished.assigns.identities == %{}
    refute_received :unexpected_request
  end

  test "a failed confirmation preserves credentials, inventory, and prior evidence for correction" do
    ctx = context()
    Req.Test.expect(__MODULE__, &Plug.Conn.send_resp(&1, 403, "private-response-canary"))
    failed = confirm(ctx, @child)
    assert failed.assigns.view.phase == "identification"
    assert failed.assigns.credentials == ctx.assigns.credentials
    assert failed.assigns.inventory == ctx.assigns.inventory
    assert failed.assigns.identities == ctx.assigns.identities
    assert failed.assigns.view.identification_id == ctx.assigns.view.identification_id
    assert failed.assigns.view.message =~ "inaccessible account"
    refute inspect(failed.assigns.view) =~ "private-response-canary"

    expect_account(@child, @parent)
    assert confirm(failed, @child).assigns.view.phase == "selection"
  end

  test "a parent overlap blocks selection but the confirmed SID remains editable" do
    expect_account(@parent, @parent)
    blocked = confirm(context(), @parent)
    assert blocked.assigns.view.phase == "identification"
    assert blocked.assigns.view.identity_blocker
    assert blocked.assigns.view.message =~ "overlap"
    assert hd(blocked.assigns.view.integrations).relationship =~ "This parent account"

    expect_account(@child, @parent)
    corrected = confirm(blocked, @child)
    assert corrected.assigns.view.phase == "selection"
    refute corrected.assigns.view.identity_blocker
    assert corrected.assigns.identities[@token].account_sid == @child
  end

  test "a worker failure during identification preserves session state" do
    ctx = context()
    monitor = make_ref()
    assigns = %{ctx.assigns | monitor: monitor, operation: make_ref(), view: %{ctx.assigns.view | phase: "identifying"}}
    working = %{ctx | assigns: assigns}
    assert {:noreply, failed} = Panel.handle_info({:DOWN, monitor, :process, self(), :killed}, working)
    assert failed.assigns.credentials == ctx.assigns.credentials
    assert failed.assigns.inventory == ctx.assigns.inventory
    assert failed.assigns.view.phase == "identification"
    assert failed.assigns.operation == nil
  end

  test "confirmed connections can be reviewed again and clearing discards manual evidence" do
    expect_account(@child, @parent)
    selected = confirm(context(), @child)
    assert {:noreply, reopened} = Panel.handle_event("review_identities", %{}, selected)
    assert reopened.assigns.view.phase == "identification"
    refute reopened.assigns.view.identification_id == selected.assigns.view.identification_id
    assert {:noreply, cleared} = Panel.handle_event("clear", %{}, reopened)
    assert cleared.assigns.identities == %{}
    assert cleared.assigns.credentials == nil
    assert cleared.assigns.inventory == nil
    assert cleared.assigns.view == Presentation.initial()
  end

  defp context do
    {:ok, credentials} = Credentials.new(@parent, "private-auth-canary", "private-vantage-canary")

    integration = %{
      token: @token,
      status: "connected",
      account_sid: nil,
      identity_hint: @child,
      identity_label: "Legacy account"
    }

    account = %{sid: @child, parent_sid: @parent, name: "Customer", status: "active"}
    inventory = %{accounts: [account], integrations: [integration], workspaces: [%{token: @workspace, name: "Finance"}]}
    view = Presentation.inventory(inventory, @parent, %{}, "initial-identification")

    assigns = %{
      credentials: credentials,
      inventory: inventory,
      identities: %{},
      view: view,
      plan: nil,
      operation: nil,
      monitor: nil
    }

    %Context{assigns: assigns, __private__: %{ref: "identification-test"}}
  end

  defp payload(ctx, sid) do
    %{"identification_id" => ctx.assigns.view.identification_id, "token" => @token, "sid" => sid, "confirmed" => true}
  end

  defp confirm(ctx, sid) do
    assert {:noreply, working} = Panel.handle_event("confirm_identity", payload(ctx, sid), ctx)
    assert working.assigns.view.phase == "identifying"
    assert {:noreply, ^working} = Panel.handle_event("confirm_identity", payload(ctx, sid), working)
    finish_worker(working)
  end

  defp finish_worker(ctx) do
    reference = ctx.assigns.operation
    assert_receive {:finished, ^reference, _result} = message, 1_000
    assert {:noreply, finished} = Panel.handle_info(message, ctx)
    finished
  end

  defp expect_account(sid, parent_sid) do
    Req.Test.expect(__MODULE__, fn conn ->
      assert conn.method == "GET"
      assert conn.request_path == "/2010-04-01/Accounts/#{sid}.json"

      Req.Test.json(conn, %{
        "sid" => sid,
        "owner_account_sid" => parent_sid,
        "friendly_name" => "Customer",
        "status" => "active"
      })
    end)
  end
end
