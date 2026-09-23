defmodule TwilioOnboarding.Core.PayloadsTest do
  use ExUnit.Case, async: true

  alias TwilioOnboarding.Core.Inventory
  alias TwilioOnboarding.Core.Payloads

  @child "AC00000000000000000000000000000002"

  test "key requests target only the selected account using Twilio's Standard default" do
    assert Payloads.key(@child, "reviewed-run") ==
             %{"AccountSid" => @child, "FriendlyName" => "vantage-reviewed-run"}
  end

  test "integration receives only the selected child key and no parent auth credential" do
    entry = %{sid: @child, name: "Customer", action: :connect, integration_token: nil, parent_auth_token: "never-send"}
    key = %{sid: "SK00000000000000000000000000000001", secret: "child-secret", auth_token: "never-send"}
    payload = Payloads.integration(entry, key)

    assert payload == %{
             "api_key" => key.sid,
             "api_secret" => "child-secret",
             "account_sid" => @child,
             "friendly_account_name" => "Customer",
             "description" => "Twilio sub-account " <> @child
           }

    assert {:ok, %{account_sid: nil, identity_hint: @child}} =
             Inventory.integration(%{
               "token" => "accss_crdntl_0000000000000001",
               "status" => "pending",
               "account_identifier" => payload["description"]
             })
  end
end
