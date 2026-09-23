defmodule TwilioOnboarding.Key do
  @moduledoc "A newly created Twilio key whose secret is never shown by inspection."

  @derive {Inspect, only: [:sid]}
  @enforce_keys [:sid, :secret]
  defstruct [:sid, :secret]

  @type t :: %__MODULE__{sid: String.t(), secret: String.t()}
end
