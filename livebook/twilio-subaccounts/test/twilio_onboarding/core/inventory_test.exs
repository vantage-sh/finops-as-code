defmodule TwilioOnboarding.Core.InventoryTest do
  use ExUnit.Case, async: true

  alias TwilioOnboarding.Core.Inventory

  @parent "AC00000000000000000000000000000001"
  @child "AC00000000000000000000000000000002"
  @integration "accss_crdntl_0000000000000001"

  test "account projection discards authentication fields and untrusted URLs" do
    raw =
      Map.merge(account(), %{
        "auth_token" => "do-not-return",
        "uri" => "https://attacker.example",
        "extra" => %{secret: "nested"}
      })

    assert Inventory.account(raw) ==
             {:ok, %{sid: @child, parent_sid: @parent, name: "Customer", status: "active"}}
  end

  test "account names are trimmed before review" do
    assert {:ok, %{name: "Customer"}} = Inventory.account(Map.put(account(), "friendly_name", " Customer "))
  end

  test "malformed account identities cannot enter a plan" do
    for sid <- [@child <> "/Keys.json", @child <> "\n", "AC123", nil, 42] do
      assert Inventory.account(Map.put(account(), "sid", sid)) == {:error, :invalid_response}
      assert Inventory.account(Map.put(account(), "owner_account_sid", sid)) == {:error, :invalid_response}
    end
  end

  test "unsafe and unbounded names are rejected without exposing them" do
    for name <- [
          "",
          "   ",
          "one\ntwo",
          "one\rtwo",
          "name\u202Etxt",
          "name\u2028next",
          String.duplicate("a", 201),
          <<255>>
        ] do
      assert Inventory.account(Map.put(account(), "friendly_name", name)) == {:error, :invalid_response}
    end
  end

  test "known inactive states are kept so selection can explain ineligibility" do
    for status <- ["suspended", "closed"] do
      assert {:ok, %{status: ^status}} = Inventory.account(Map.put(account(), "status", status))
    end

    assert Inventory.account(Map.put(account(), "status", "unrecognized")) == {:error, :invalid_response}
  end

  test "exact account SIDs and legacy markers are hints without verified identity" do
    for identifier <- [@child, "Twilio sub-account " <> @child] do
      assert Inventory.integration(integration(identifier)) ==
               {:ok,
                %{
                  token: @integration,
                  account_sid: nil,
                  identity_hint: @child,
                  identity_label: identifier,
                  status: "imported"
                }}
    end
  end

  test "substring matches and ambiguous identity fields remain blockers" do
    for identifier <- [
          nil,
          "Customer " <> @child,
          @child <> "\n",
          "Twilio sub-account " <> @child <> " extra",
          "Twilio sub-account " <> @child <> "\n",
          @child <> " " <> @parent,
          12,
          %{}
        ] do
      raw =
        Map.merge(integration(identifier), %{
          "account_sid" => @child,
          "description" => "Twilio sub-account " <> @child,
          "api_secret" => "do-not-return"
        })

      assert {:ok, normalized} = Inventory.integration(raw)

      assert Map.take(normalized, [:token, :account_sid, :identity_hint, :status]) ==
               %{token: @integration, account_sid: nil, identity_hint: nil, status: "imported"}

      refute Map.has_key?(normalized, :api_secret)
    end
  end

  test "integration labels retain exact safe metadata for confirmation snapshots" do
    assert {:ok, %{identity_label: " Customer ", identity_hint: nil}} =
             Inventory.integration(integration(" Customer "))

    for unsafe <- [nil, "", "  ", "Customer\n", "Customer\u202E", String.duplicate("x", 201), <<255>>] do
      assert {:ok, %{identity_label: nil}} = Inventory.integration(integration(unsafe))
    end
  end

  test "integration paths cannot contain malformed tokens" do
    for token <- [@integration <> "/", @integration <> "\n", "wrkspc_0000000000000001", nil] do
      assert Inventory.integration(Map.put(integration(@child), "token", token)) == {:error, :invalid_response}
    end
  end

  test "workspace projection excludes all fields except name and token" do
    assert Inventory.workspace(%{
             "token" => "wrkspc_0000000000000001",
             "name" => " Customer workspace ",
             "auth_token" => "secret"
           }) ==
             {:ok, %{token: "wrkspc_0000000000000001", name: "Customer workspace"}}
  end

  test "workspace cannot introduce an unsafe destination or display name" do
    assert Inventory.workspace(%{"token" => "wrkspc_0000000000000001/other", "name" => "Workspace"}) ==
             {:error, :invalid_response}

    assert Inventory.workspace(%{"token" => "wrkspc_0000000000000001", "name" => "Workspace\n"}) ==
             {:error, :invalid_response}
  end

  test "wrong response shapes return fixed errors" do
    for raw <- [nil, [], "secret", %{}, %{"sid" => @child}] do
      assert Inventory.account(raw) == {:error, :invalid_response}
      assert Inventory.integration(raw) == {:error, :invalid_response}
      assert Inventory.workspace(raw) == {:error, :invalid_response}
    end
  end

  defp account do
    %{"sid" => @child, "owner_account_sid" => @parent, "friendly_name" => "Customer", "status" => "active"}
  end

  defp integration(identifier) do
    %{"token" => @integration, "account_identifier" => identifier, "status" => "imported"}
  end
end
