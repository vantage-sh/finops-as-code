defmodule TwilioOnboarding.Core.Storage do
  @moduledoc "Defines the platform and permission guarantees required by local recovery storage."

  @doc "Accepts only the Unix platforms supported by the recovery implementation."
  @spec supported_platform?(term()) :: boolean()
  def supported_platform?({:unix, platform}) when platform in [:darwin, :linux], do: true
  def supported_platform?(_platform), do: false

  @doc "Checks the actual permission bits rather than trusting a successful chmod call."
  @spec private_mode?(non_neg_integer(), non_neg_integer()) :: boolean()
  def private_mode?(actual, expected), do: Bitwise.band(actual, 0o7777) == expected
end
