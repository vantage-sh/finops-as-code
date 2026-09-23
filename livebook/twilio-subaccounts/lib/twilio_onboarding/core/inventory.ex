defmodule TwilioOnboarding.Core.Inventory do
  @moduledoc "Extracts the small, non-secret inventory needed for account selection."

  alias TwilioOnboarding.Core.Identifiers

  @account_statuses ~w(active suspended closed)
  @integration_statuses ~w(connected error pending importing imported disconnected)

  @type account :: %{sid: String.t(), parent_sid: String.t(), name: String.t(), status: String.t()}
  @type integration :: %{
          token: String.t(),
          account_sid: String.t() | nil,
          identity_hint: String.t() | nil,
          identity_label: String.t() | nil,
          status: String.t()
        }
  @type workspace :: %{token: String.t(), name: String.t()}

  @doc "Discards Twilio response fields other than account identity, display name, and status."
  @spec account(term()) :: {:ok, account()} | {:error, :invalid_response}
  def account(%{"sid" => sid, "owner_account_sid" => parent, "friendly_name" => name, "status" => status}) do
    with true <- Identifiers.account_sid?(sid),
         true <- Identifiers.account_sid?(parent),
         true <- status in @account_statuses,
         {:ok, name} <- display_name(name) do
      {:ok, %{sid: sid, parent_sid: parent, name: name, status: status}}
    else
      _ -> {:error, :invalid_response}
    end
  end

  def account(_), do: {:error, :invalid_response}

  @doc "Extracts a Twilio integration with display hints that do not establish account identity."
  @spec integration(term()) :: {:ok, integration()} | {:error, :invalid_response}
  def integration(%{"token" => token, "status" => status} = raw) do
    with true <- Identifiers.integration_token?(token),
         true <- status in @integration_statuses do
      {:ok,
       %{
         token: token,
         account_sid: nil,
         identity_hint: account_identifier(raw["account_identifier"]),
         identity_label: identity_label(raw["account_identifier"]),
         status: status
       }}
    else
      _ -> {:error, :invalid_response}
    end
  end

  def integration(_), do: {:error, :invalid_response}

  @doc "Extracts a safe Vantage workspace identity and display name."
  @spec workspace(term()) :: {:ok, workspace()} | {:error, :invalid_response}
  def workspace(%{"token" => token, "name" => name}) do
    with true <- Identifiers.workspace_token?(token),
         {:ok, name} <- display_name(name) do
      {:ok, %{token: token, name: name}}
    else
      _ -> {:error, :invalid_response}
    end
  end

  def workspace(_), do: {:error, :invalid_response}

  defp account_identifier("Twilio sub-account " <> sid) do
    if Identifiers.account_sid?(sid) do
      sid
    end
  end

  defp account_identifier(value) do
    if Identifiers.account_sid?(value) do
      value
    end
  end

  defp identity_label(value) do
    case display_name(value) do
      {:ok, _trimmed} -> value
      {:error, _reason} -> nil
    end
  end

  defp display_name(name) when is_binary(name) and byte_size(name) <= 800 do
    with true <- String.valid?(name),
         false <- Regex.match?(~r/[\p{C}\p{Zl}\p{Zp}]/u, name),
         trimmed = String.trim(name),
         true <- String.length(trimmed) in 1..200 do
      {:ok, trimmed}
    else
      _ -> {:error, :invalid_response}
    end
  end

  defp display_name(_), do: {:error, :invalid_response}
end
