defmodule TwilioOnboarding.CredentialValidationTest do
  use ExUnit.Case, async: false

  import Kino.Test

  alias TwilioOnboarding.Credentials
  alias TwilioOnboarding.Notebook.Panel

  @variables ~w(LB_TWILIO_ACCOUNT_SID LB_TWILIO_AUTH_TOKEN LB_VANTAGE_API_TOKEN)
  @parent "AC00000000000000000000000000000001"
  @auth_token "parent-auth-token-canary-12345678"
  @vantage_token "vantage-api-token-canary-12345678"

  setup :configure_livebook_bridge

  setup do
    environment = Map.new(@variables, &{&1, System.get_env(&1)})
    previous_options = Req.default_options()
    Enum.each(@variables, &System.delete_env/1)
    Req.default_options(plug: {Req.Test, __MODULE__})
    Req.Test.set_req_test_to_shared()
    Req.Test.verify_on_exit!()

    on_exit(fn ->
      Enum.each(environment, fn
        {name, nil} -> System.delete_env(name)
        {name, value} -> System.put_env(name, value)
      end)

      Req.default_options(previous_options)
      Req.Test.set_req_test_to_private()
    end)

    :ok
  end

  test "Validate credentials with no secrets explains setup without contacting an API" do
    prevent_requests()
    panel = Panel.new()
    connect(panel)
    push_event(panel, "discover", %{})

    assert_broadcast_event(panel, "state", %{phase: "discovering"})
    assert_broadcast_event(panel, "state", %{phase: "ready", message: message} = view)
    assert message =~ "Livebook's Secrets panel"
    assert message =~ "TWILIO_ACCOUNT_SID"
    assert message =~ "TWILIO_AUTH_TOKEN"
    assert message =~ "VANTAGE_API_TOKEN"
    assert message =~ "grant this notebook access"
    refute message =~ "recovery"
    assert view.accounts == []
    assert view.workspaces == []
    refute_received :unexpected_request
  end

  test "malformed credentials preserve setup instructions and never expose supplied values" do
    prevent_requests()
    set_credentials("malformed-account-canary")
    panel = Panel.new()
    connect(panel)
    push_event(panel, "discover", %{})

    assert_broadcast_event(panel, "state", %{phase: "discovering"})
    assert_broadcast_event(panel, "state", %{phase: "ready", message: message} = view)
    assert message =~ "Account SID"
    assert message =~ "32 hexadecimal characters"
    refute message =~ "recovery"

    for secret <- ["malformed-account-canary", @auth_token, @vantage_token], do: refute(inspect(view) =~ secret)
    refute_received :unexpected_request
  end

  test "missing and invalid local credentials have different safe reasons" do
    assert Credentials.from_env() == {:error, :missing_credentials}

    for value <- [nil, "", "   "] do
      assert Credentials.new(@parent, value, @vantage_token) == {:error, :missing_credentials}
    end

    assert Credentials.new("invalid-sid", @auth_token, @vantage_token) == {:error, :invalid_credentials}
    assert Credentials.new(@parent, "contains whitespace canary", @vantage_token) == {:error, :invalid_credentials}
    assert Credentials.new(@parent, @auth_token, "short") == {:error, :invalid_credentials}
    assert Credentials.new(@parent, @auth_token, 42) == {:error, :invalid_credentials}
    assert Credentials.new(@parent, @auth_token, <<255>> <> String.duplicate("a", 20)) == {:error, :invalid_credentials}
  end

  test "read failures explain that validation made no changes" do
    set_credentials(@parent)
    Req.Test.expect(__MODULE__, &Plug.Conn.send_resp(&1, 503, "provider-response-canary"))
    panel = Panel.new()
    connect(panel)
    push_event(panel, "discover", %{})

    assert_broadcast_event(panel, "state", %{phase: "discovering"})
    assert_broadcast_event(panel, "state", %{phase: "attention", message: message} = view)
    assert message =~ "Check your connection"
    assert message =~ "No changes were made"
    refute message =~ "recovery"
    refute inspect(view) =~ "provider-response-canary"
    refute inspect(view) =~ @auth_token
    refute inspect(view) =~ @vantage_token
  end

  test "a crashed discovery worker gives validation guidance without write-recovery advice" do
    set_credentials(@parent)
    observer = self()

    Req.Test.expect(__MODULE__, fn conn ->
      send(observer, {:request_worker, self()})

      receive do
        :continue -> Req.Test.json(conn, %{})
      end
    end)

    panel = Panel.new()
    connect(panel)
    push_event(panel, "discover", %{})
    assert_broadcast_event(panel, "state", %{phase: "discovering"})
    assert_receive {:request_worker, worker}
    Process.exit(worker, :kill)

    assert_broadcast_event(panel, "state", %{phase: "attention", message: message})
    assert message =~ "Validation could not be completed"
    assert message =~ "No changes were made"
    refute message =~ "recovery"
    refute message =~ "unknown"
  end

  defp set_credentials(parent) do
    System.put_env("LB_TWILIO_ACCOUNT_SID", parent)
    System.put_env("LB_TWILIO_AUTH_TOKEN", @auth_token)
    System.put_env("LB_VANTAGE_API_TOKEN", @vantage_token)
  end

  defp prevent_requests do
    observer = self()

    Req.Test.stub(__MODULE__, fn conn ->
      send(observer, :unexpected_request)
      Plug.Conn.send_resp(conn, 503, "")
    end)
  end
end
