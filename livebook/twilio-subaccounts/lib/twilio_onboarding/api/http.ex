defmodule TwilioOnboarding.API.HTTP do
  @moduledoc "Bounded HTTPS requests to fixed provider origins without redirects or raw errors."

  alias TwilioOnboarding.Credentials

  @type provider :: :twilio | :twilio_iam | :vantage
  @type reason :: :unauthorized | :forbidden | :rate_limited | :rejected | :uncertain | :invalid_response | :unavailable
  @max_body 4_194_304

  @doc "Send one API request and return decoded data or a safe error category."
  @spec call(provider(), Credentials.t(), atom(), String.t(), keyword()) :: {:ok, map()} | {:error, reason()}
  def call(provider, credentials, method, path, options \\ []) do
    with true <- safe_path?(path),
         {:ok, response} <- request(provider, credentials, method, path, options, 0) do
      decode(response, method)
    else
      false -> {:error, :invalid_response}
      {:error, _reason} -> {:error, transport_reason(method)}
    end
  rescue
    _exception -> {:error, transport_reason(method)}
  end

  @doc "Return the fixed origin for a provider's API."
  @spec origin(provider()) :: String.t()
  def origin(:twilio), do: "https://api.twilio.com"
  def origin(:twilio_iam), do: "https://iam.twilio.com"
  def origin(:vantage), do: "https://api.vantage.sh"

  defp request(provider, credentials, method, path, options, attempt) do
    request_options = [
      method: method,
      url: origin(provider) <> path,
      auth: authorization(provider, credentials),
      redirect: false,
      retry: false,
      retry_log_level: false,
      decode_body: false,
      compressed: false,
      receive_timeout: 60_000,
      finch: [
        pool_timeout: 10_000,
        request_timeout: 60_000,
        conn_opts: [transport_opts: [timeout: 10_000, verify: :verify_peer]]
      ],
      into: &collect/2
    ]

    request_options
    |> Req.request(Keyword.take(options, [:params, :json, :form]))
    |> retry_rate_limit(provider, credentials, method, path, options, attempt)
  end

  defp retry_rate_limit({:ok, %{status: 429}}, provider, credentials, method, path, options, attempt) when attempt < 2 do
    Process.sleep(1_000 * Integer.pow(2, attempt))
    request(provider, credentials, method, path, options, attempt + 1)
  end

  defp retry_rate_limit(result, _provider, _credentials, _method, _path, _options, _attempt), do: result

  defp collect({:data, chunk}, {request, response}) do
    body = response.body || ""

    if byte_size(body) + byte_size(chunk) <= @max_body do
      {:cont, {request, %{response | body: body <> chunk}}}
    else
      {:halt, {request, %{response | status: 599, body: ""}}}
    end
  end

  defp authorization(:vantage, %Credentials{vantage_token: token}), do: {:bearer, token}
  defp authorization(_provider, %Credentials{parent_sid: sid, auth_token: token}), do: {:basic, sid <> ":" <> token}

  defp decode(%{status: 204}, _method), do: {:ok, %{}}

  defp decode(%{status: status, body: body}, method) when status in 200..299 do
    case Jason.decode(body) do
      {:ok, decoded} when is_map(decoded) -> {:ok, decoded}
      _other -> {:error, transport_reason(method)}
    end
  end

  defp decode(%{status: 401}, _method), do: {:error, :unauthorized}
  defp decode(%{status: 403}, _method), do: {:error, :forbidden}
  defp decode(%{status: 429}, _method), do: {:error, :rate_limited}
  defp decode(%{status: status}, _method) when status in [400, 404, 409, 422], do: {:error, :rejected}
  defp decode(_response, method), do: {:error, transport_reason(method)}

  defp transport_reason(:get), do: :unavailable
  defp transport_reason(_method), do: :uncertain

  defp safe_path?(path),
    do:
      String.starts_with?(path, "/") and not String.starts_with?(path, "//") and
        not String.contains?(path, ["?", "#", "\\", "\r", "\n"])
end
