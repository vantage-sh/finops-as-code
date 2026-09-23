defmodule TwilioOnboarding.API.Twilio do
  @moduledoc "Twilio account discovery and child-key lifecycle through fixed US1 endpoints."

  alias TwilioOnboarding.API.HTTP
  alias TwilioOnboarding.API.Pages
  alias TwilioOnboarding.Core.Identifiers
  alias TwilioOnboarding.Core.Inventory
  alias TwilioOnboarding.Core.Payloads
  alias TwilioOnboarding.Credentials
  alias TwilioOnboarding.Key

  @doc "List every account visible to the parent credentials without retaining auth tokens."
  @spec list_accounts(Credentials.t()) :: {:ok, [map()]} | {:error, atom()}
  def list_accounts(credentials) do
    Pages.list(:twilio, credentials, "/2010-04-01/Accounts.json", [PageSize: 1000], "accounts", &Inventory.account/1)
  end

  @doc "Read one exact account identity without retaining authentication fields."
  @spec get_account(Credentials.t(), String.t()) :: {:ok, Inventory.account()} | {:error, atom()}
  def get_account(credentials, sid) do
    with true <- Identifiers.account_sid?(sid),
         {:ok, body} <- HTTP.call(:twilio, credentials, :get, "/2010-04-01/Accounts/#{sid}.json"),
         {:ok, %{sid: ^sid} = account} <- Inventory.account(body) do
      {:ok, account}
    else
      false -> {:error, :invalid_account_sid}
      {:ok, _account} -> {:error, :invalid_response}
      {:error, _reason} = error -> error
    end
  end

  @doc "Create a Standard key for one validated child account."
  @spec create_key(Credentials.t(), String.t(), String.t()) :: {:ok, Key.t()} | {:error, atom()}
  def create_key(credentials, sid, run_id) do
    with {:ok, body} <- HTTP.call(:twilio_iam, credentials, :post, "/v1/Keys", form: Payloads.key(sid, run_id)) do
      key(body)
    end
  end

  @doc "Revoke one known key on a child account."
  @spec delete_key(Credentials.t(), String.t(), String.t()) :: :ok | {:error, atom()}
  def delete_key(credentials, sid, key_sid) do
    if Regex.match?(~r/\AAC[0-9a-fA-F]{32}\z/, sid) and Regex.match?(~r/\ASK[0-9a-fA-F]{32}\z/, key_sid) do
      revoke(credentials, "/2010-04-01/Accounts/#{sid}/Keys/#{key_sid}.json")
    else
      {:error, :invalid_response}
    end
  end

  defp key(%{"sid" => sid, "secret" => secret}) when is_binary(sid) and is_binary(secret) do
    if Regex.match?(~r/\ASK[0-9a-fA-F]{32}\z/, sid) and byte_size(secret) in 16..256 do
      {:ok, %Key{sid: sid, secret: secret}}
    else
      {:error, :uncertain}
    end
  end

  defp key(_body), do: {:error, :uncertain}

  defp revoke(credentials, path) do
    case HTTP.call(:twilio, credentials, :delete, path) do
      {:ok, _body} -> :ok
      error -> error
    end
  end
end
