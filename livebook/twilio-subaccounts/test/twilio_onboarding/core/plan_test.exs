defmodule TwilioOnboarding.Core.PlanTest do
  use ExUnit.Case, async: true

  alias TwilioOnboarding.Core.Plan

  @parent "AC00000000000000000000000000000001"
  @child "AC00000000000000000000000000000002"
  @other "AC00000000000000000000000000000003"
  @workspace "wrkspc_0000000000000001"
  @integration "accss_crdntl_0000000000000001"

  test "reviewed entries distinguish connections from accounts already present" do
    assert Plan.build(@parent, [account(@other), account(@child)], [integration(@child)], [@other, @child], @workspace) ==
             {:ok,
              %{
                parent_sid: @parent,
                workspace_token: @workspace,
                entries: [
                  %{sid: @child, name: @child, action: :skip, integration_token: @integration},
                  %{sid: @other, name: @other, action: :connect, integration_token: nil}
                ]
              }}
  end

  test "unselected accounts never become writes" do
    assert {:ok, %{entries: [%{sid: @child, action: :connect}]}} =
             Plan.build(@parent, [account(@other), account(@child)], [], [@child], @workspace)
  end

  test "unknown existing identity blocks creation even for a different selected child" do
    assert Plan.build(@parent, [account(@child)], [integration(nil)], [@child], @workspace) ==
             {:error, :unidentified_integration}
  end

  test "a parent connection blocks overlapping child costs regardless of status" do
    existing = Map.put(integration(@parent), :status, "disconnected")

    assert Plan.build(@parent, [account(@child)], [existing], [@child], @workspace) ==
             {:error, :parent_already_connected}
  end

  test "duplicate connections cannot silently choose one token" do
    duplicate = Map.put(integration(@child), :token, "accss_crdntl_0000000000000002")

    assert Plan.build(@parent, [account(@child)], [integration(@child), duplicate], [@child], @workspace) ==
             {:error, :duplicate_integrations}
  end

  test "duplicate selections and empty selections fail before execution" do
    assert Plan.build(@parent, [account(@child)], [], [@child, @child], @workspace) == {:error, :duplicate_selection}
    assert Plan.build(@parent, [account(@child)], [], [], @workspace) == {:error, :no_accounts_selected}
  end

  test "parent, foreign, inactive, and unknown accounts cannot be selected" do
    foreign = Map.put(account(@other), :parent_sid, @other)
    parent = account(@parent)

    for invalid <- [
          foreign,
          parent,
          Map.put(account(@child), :status, "closed"),
          Map.put(account(@child), :status, "suspended")
        ] do
      assert Plan.build(@parent, [invalid], [], [invalid.sid], @workspace) == {:error, :invalid_selection}
    end

    assert Plan.build(@parent, [account(@child)], [], [@other], @workspace) == {:error, :invalid_selection}
  end

  test "non-active unselected accounts do not prevent eligible work" do
    inactive = Map.put(account(@other), :status, "closed")

    assert {:ok, %{entries: [%{sid: @child}]}} =
             Plan.build(@parent, [inactive, account(@child)], [], [@child], @workspace)
  end

  test "malformed or duplicate inventory fails closed" do
    for accounts <- [[%{}], [account(@child), account(@child)], [%{account(@child) | name: " padded "}]] do
      assert Plan.build(@parent, accounts, [], [@child], @workspace) == {:error, :invalid_inventory}
    end

    assert Plan.build(@parent, [account(@child)], [integration(@child), integration(@child)], [@child], @workspace) ==
             {:error, :invalid_inventory}

    assert Plan.build(@parent, "secret", [], [@child], @workspace) == {:error, :invalid_inventory}
  end

  test "invalid destination identifiers cannot become part of a plan" do
    assert Plan.build(@parent <> "/", [account(@child)], [], [@child], @workspace) == {:error, :invalid_destination}
    assert Plan.build(@parent, [account(@child)], [], [@child], @workspace <> "/") == {:error, :invalid_destination}
  end

  test "duplicate display names receive unique deterministic suffixes before review" do
    accounts = [Map.put(account(@child), :name, "Customer"), Map.put(account(@other), :name, "Customer")]
    assert {:ok, plan} = Plan.build(@parent, accounts, [], [@other, @child], @workspace)
    assert {:ok, ^plan} = Plan.build(@parent, Enum.reverse(accounts), [], [@child, @other], @workspace)
    assert Enum.map(plan.entries, & &1.name) == ["Customer (" <> @child <> ")", "Customer (" <> @other <> ")"]
  end

  test "name collision fallback remains unique when a name impersonates a generated suffix" do
    third = "AC00000000000000000000000000000004"

    accounts = [
      Map.put(account(@child), :name, "Customer"),
      Map.put(account(@other), :name, "Customer"),
      Map.put(account(third), :name, "Customer (" <> @child <> ")")
    ]

    assert {:ok, plan} = Plan.build(@parent, accounts, [], [@child, @other, third], @workspace)
    assert Enum.map(plan.entries, & &1.name) == [@child, @other, third]
  end

  test "generated names stay bounded even when the source name is long" do
    name = String.duplicate("a", 200)
    accounts = [Map.put(account(@child), :name, name), Map.put(account(@other), :name, name)]

    assert {:ok, plan} = Plan.build(@parent, accounts, [], [@child, @other], @workspace)

    assert Enum.map(plan.entries, & &1.name) == [
             String.duplicate("a", 160) <> " (" <> @child <> ")",
             String.duplicate("a", 160) <> " (" <> @other <> ")"
           ]
  end

  test "extra fields cannot leak from normalized inputs into the plan" do
    child = Map.put(account(@child), :auth_token, "do-not-return")

    assert Plan.build(@parent, [child], [], [@child], @workspace) ==
             {:ok,
              %{
                parent_sid: @parent,
                workspace_token: @workspace,
                entries: [%{sid: @child, name: @child, action: :connect, integration_token: nil}]
              }}
  end

  defp account(sid), do: %{sid: sid, parent_sid: @parent, name: sid, status: "active"}
  defp integration(sid), do: %{token: @integration, account_sid: sid, status: "imported"}
end
