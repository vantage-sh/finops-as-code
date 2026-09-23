defmodule TwilioOnboarding.IdentificationTest do
  use ExUnit.Case, async: false

  import ExUnit.CaptureLog

  alias TwilioOnboarding.API.Identification
  alias TwilioOnboarding.API.Twilio
  alias TwilioOnboarding.Core.Inventory
  alias TwilioOnboarding.Credentials

  @parent "AC00000000000000000000000000000001"
  @child "AC00000000000000000000000000000002"
  @other "AC00000000000000000000000000000003"
  @integration "accss_crdntl_0000000000000001"
  @auth_token "parent-auth-token-canary-12345678"

  setup do
    previous = Req.default_options()
    Req.default_options(plug: {Req.Test, __MODULE__})
    Req.Test.verify_on_exit!()
    on_exit(fn -> Req.default_options(previous) end)
    :ok
  end

  test "confirmation reads the exact Twilio account and discards secret response fields" do
    Req.Test.expect(__MODULE__, fn conn ->
      assert {conn.method, conn.host, conn.request_path} ==
               {"GET", "api.twilio.com", "/2010-04-01/Accounts/#{@child}.json"}

      Req.Test.json(conn, Map.put(account(), "auth_token", "returned-auth-token-canary"))
    end)

    assert Identification.confirm(credentials(), [integration()], @integration, @child) ==
             {:ok,
              %{
                account_sid: @child,
                parent_sid: @parent,
                source: :confirmed,
                identity_label: "Customer"
              }}
  end

  test "invalid and missing integration tokens or account SIDs fail before any request" do
    test_pid = self()

    Req.Test.stub(__MODULE__, fn conn ->
      send(test_pid, :unexpected_request)
      Req.Test.json(conn, account())
    end)

    for sid <- [nil, "AC123", @child <> "/Keys.json", @child <> "\n"] do
      assert Identification.confirm(credentials(), [integration()], @integration, sid) == {:error, :invalid_account_sid}
      assert Twilio.get_account(credentials(), sid) == {:error, :invalid_account_sid}
    end

    for {integrations, token} <- [
          {[], @integration},
          {[integration()], @integration <> "/"},
          {[integration(), integration()], @integration}
        ] do
      assert Identification.confirm(credentials(), integrations, token, @child) == {:error, :invalid_integration}
    end

    refute_received :unexpected_request
  end

  test "a successful response for a different SID is rejected" do
    Req.Test.expect(__MODULE__, &Req.Test.json(&1, Map.put(account(), "sid", @other)))

    assert Identification.confirm(credentials(), [integration()], @integration, @child) == {:error, :invalid_response}
  end

  test "a readable account owned by another parent is verified with its actual owner" do
    Req.Test.expect(__MODULE__, &Req.Test.json(&1, Map.put(account(), "owner_account_sid", @other)))

    assert {:ok, %{account_sid: @child, parent_sid: @other, source: :confirmed}} =
             Identification.confirm(credentials(), [integration()], @integration, @child)
  end

  test "inaccessible accounts remain unresolved without exposing provider messages" do
    logs =
      capture_log(fn ->
        for {status, reason} <- [{401, :unauthorized}, {403, :forbidden}, {404, :rejected}, {503, :unavailable}] do
          Req.Test.expect(__MODULE__, &Plug.Conn.send_resp(&1, status, @auth_token))

          assert Identification.confirm(credentials(), [integration()], @integration, @child) == {:error, reason}
        end
      end)

    refute logs =~ @auth_token
  end

  test "malformed Twilio response fields remain unresolved" do
    for raw <- [Map.delete(account(), "owner_account_sid"), Map.put(account(), "friendly_name", "unsafe\n"), %{}] do
      Req.Test.expect(__MODULE__, &Req.Test.json(&1, raw))
      assert Identification.confirm(credentials(), [integration()], @integration, @child) == {:error, :invalid_response}
    end
  end

  defp integration do
    {:ok, integration} =
      Inventory.integration(%{"token" => @integration, "account_identifier" => "Customer", "status" => "imported"})

    integration
  end

  defp account do
    %{"sid" => @child, "owner_account_sid" => @parent, "friendly_name" => "Customer", "status" => "active"}
  end

  defp credentials do
    %Credentials{parent_sid: @parent, auth_token: @auth_token, vantage_token: "vantage-token-canary-12345678"}
  end
end
