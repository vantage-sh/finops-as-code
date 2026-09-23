defmodule TwilioOnboarding.Core.IdentityTest do
  use ExUnit.Case, async: true

  alias TwilioOnboarding.Core.Identity
  alias TwilioOnboarding.Core.Inventory

  @parent "AC00000000000000000000000000000001"
  @child "AC00000000000000000000000000000002"
  @other "AC00000000000000000000000000000003"
  @integration "accss_crdntl_0000000000000001"
  @other_integration "accss_crdntl_0000000000000002"

  test "a spoofed marker and caller-supplied SID cannot resolve an integration" do
    integration = integration("Twilio sub-account " <> @other)
    assert integration.identity_hint == @other

    assert Identity.resolve([Map.put(integration, :account_sid, @other)], %{}) == [integration]
  end

  test "confirmed evidence resolves exact tokens and labels while retaining status" do
    integration = integration("Customer", "error")
    assert {:ok, evidence} = Identity.confirm([integration], @integration, account())

    assert evidence == %{
             account_sid: @child,
             parent_sid: @parent,
             source: :confirmed,
             identity_label: "Customer"
           }

    assert Identity.resolve([integration], %{@integration => evidence}) ==
             [%{integration | account_sid: @child}]

    for identities <- [
          %{@other_integration => evidence},
          %{@integration => %{evidence | identity_label: "Changed"}},
          %{@integration => %{evidence | source: :hint}},
          %{@integration => %{evidence | account_sid: @child <> "/"}},
          %{@integration => %{evidence | parent_sid: nil}}
        ] do
      assert Identity.resolve([integration], identities) == [integration]
    end

    changed = %{integration | identity_label: "Customer "}
    assert Identity.resolve([changed], %{@integration => evidence}) == [changed]
  end

  test "confirmation accepts a verified different owner without changing it" do
    assert {:ok, %{account_sid: @child, parent_sid: @other}} =
             Identity.confirm([integration()], @integration, %{account() | parent_sid: @other})
  end

  test "missing ambiguous and invalid integration tokens cannot be confirmed" do
    for {integrations, token} <- [
          {[], @integration},
          {[integration()], @other_integration},
          {[integration()], @integration <> "/"},
          {[integration(), integration()], @integration}
        ] do
      assert Identity.confirm(integrations, token, account()) == {:error, :invalid_integration}
    end

    assert {:ok, evidence} = Identity.confirm([integration()], @integration, account())

    assert Identity.resolve([integration(), integration()], %{@integration => evidence}) ==
             [integration(), integration()]
  end

  test "malformed account responses produce a fixed error" do
    for account <- [nil, %{}, %{account() | sid: "invalid-secret"}, %{account() | parent_sid: nil}] do
      assert Identity.confirm([integration()], @integration, account) == {:error, :invalid_response}
    end
  end

  test "successful journal records establish the exact created identity" do
    for outcome <- ["integration_created", "complete"] do
      records = %{@child => record(outcome)}

      assert Identity.from_records(records, [integration()], [account()]) == %{
               @integration => %{
                 account_sid: @child,
                 parent_sid: @parent,
                 source: :created,
                 identity_label: "Customer"
               }
             }
    end
  end

  test "pending or incomplete journal evidence never establishes identity" do
    for outcome <- ["key_created", "integration_pending", "integration_unknown", "cleanup_failed", nil] do
      assert Identity.from_records(%{@child => record(outcome)}, [integration()], [account()]) == %{}
    end

    records = %{@child => record("complete")}
    assert Identity.from_records(records, [], [account()]) == %{}
    assert Identity.from_records(records, [integration()], []) == %{}
    assert Identity.from_records(records, [integration()], [%{account() | parent_sid: nil}]) == %{}

    assert Identity.from_records(
             %{@child => %{record("complete") | integration_token: @other_integration}},
             [integration()],
             [account()]
           ) == %{}
  end

  test "conflicting journal records cannot choose an arbitrary SID for one integration" do
    records = %{@child => record("complete"), @other => %{record("complete") | sid: @other}}
    accounts = [account(), %{account() | sid: @other}]
    assert Identity.from_records(records, [integration()], accounts) == %{}
  end

  defp integration(label \\ "Customer", status \\ "imported") do
    {:ok, integration} =
      Inventory.integration(%{"token" => @integration, "account_identifier" => label, "status" => status})

    integration
  end

  defp account do
    %{sid: @child, parent_sid: @parent, name: "Customer", status: "active"}
  end

  defp record(outcome) do
    %{sid: @child, integration_token: @integration, outcome: outcome}
  end
end
