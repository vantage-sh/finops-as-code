defmodule TwilioOnboarding.Core.ErrorsTest do
  use ExUnit.Case, async: true

  alias TwilioOnboarding.Core.Errors

  test "arbitrary remote errors never appear in customer output" do
    generic = Errors.message(:unrecognized)

    for reason <- [
          "parent-auth-token",
          {:error, %{api_secret: "secret"}},
          %{body: "password"},
          %RuntimeError{message: "sensitive response"}
        ] do
      assert Errors.message(reason) == generic
    end
  end

  test "identity failures explain the action customers need to take" do
    assert Errors.message(:unidentified_integration) =~ "Review it in Vantage"
    assert Errors.message(:parent_already_connected) =~ "overlap"
    assert Errors.message(:outcome_unknown) =~ "Reconcile"
  end

  test "unknown validation errors stay secret-safe and do not imply writes occurred" do
    for reason <- [:outcome_unknown, :rejected, {:unexpected, "secret-canary"}] do
      message = Errors.validation_message(reason)
      assert message =~ "No changes were made"
      refute message =~ "recovery"
      refute message =~ "secret-canary"
    end

    assert Errors.message(:outcome_unknown) =~ "Reconcile"
    assert Errors.message(:uncertain) =~ "Reconcile"
  end

  test "identification errors preserve correction guidance without exposing provider responses" do
    assert Errors.identification_message(:forbidden) =~ "inaccessible account"
    message = Errors.identification_message(%{body: "secret-canary"})
    assert message =~ "confirmations are preserved"
    refute message =~ "secret-canary"
  end
end
