defmodule TwilioOnboarding.Credentials do
  @moduledoc "Session credentials with a redacted inspection representation."

  @derive {Inspect, only: [:parent_sid]}
  @enforce_keys [:parent_sid, :auth_token, :vantage_token]
  defstruct [:parent_sid, :auth_token, :vantage_token]

  @type t :: %__MODULE__{parent_sid: String.t(), auth_token: String.t(), vantage_token: String.t()}
  @type reason :: :missing_credentials | :invalid_credentials

  @doc "Read credentials from the local Livebook session environment."
  @spec from_env() :: {:ok, t()} | {:error, reason()}
  def from_env do
    new(
      System.get_env("LB_TWILIO_ACCOUNT_SID"),
      System.get_env("LB_TWILIO_AUTH_TOKEN"),
      System.get_env("LB_VANTAGE_API_TOKEN")
    )
  end

  @doc "Validate credentials without retaining malformed input."
  @spec new(term(), term(), term()) :: {:ok, t()} | {:error, reason()}
  def new(parent_sid, auth_token, vantage_token) do
    cond do
      Enum.any?([parent_sid, auth_token, vantage_token], &missing?/1) ->
        {:error, :missing_credentials}

      valid_sid?(parent_sid) and valid_secret?(auth_token) and valid_secret?(vantage_token) ->
        {:ok, %__MODULE__{parent_sid: parent_sid, auth_token: auth_token, vantage_token: vantage_token}}

      true ->
        {:error, :invalid_credentials}
    end
  end

  @doc "Bind recovery records to the Vantage credential without saving its value."
  @spec fingerprint(t()) :: String.t()
  def fingerprint(%__MODULE__{vantage_token: token}) do
    :sha256 |> :crypto.hash(token) |> Base.encode16(case: :lower)
  end

  defp missing?(nil), do: true
  defp missing?(value) when is_binary(value), do: String.trim(value) == ""
  defp missing?(_value), do: false

  defp valid_sid?(value) when is_binary(value), do: Regex.match?(~r/\AAC[0-9a-fA-F]{32}\z/, value)
  defp valid_sid?(_value), do: false

  defp valid_secret?(value) when is_binary(value),
    do: String.valid?(value) and byte_size(value) in 16..4096 and not Regex.match?(~r/\s/, value)

  defp valid_secret?(_value), do: false
end
