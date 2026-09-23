defmodule TwilioOnboarding.API.Pages do
  @moduledoc "Read complete inventories while rejecting foreign or looping pagination links."

  alias TwilioOnboarding.API.HTTP
  alias TwilioOnboarding.Credentials

  @type normalizer :: (map() -> {:ok, map()} | {:error, atom()})

  @doc "Fetch and normalize every page from one fixed API resource."
  @spec list(HTTP.provider(), Credentials.t(), String.t(), keyword(), String.t(), normalizer()) ::
          {:ok, [map()]} | {:error, atom()}
  def list(provider, credentials, path, params, collection, normalize) do
    walk(provider, credentials, path, params, collection, normalize, %{}, [])
  end

  defp walk(provider, credentials, path, params, collection, normalize, seen, records) do
    cursor =
      params |> Enum.map(fn {key, value} -> {to_string(key), to_string(value)} end) |> Enum.sort() |> URI.encode_query()

    with false <- Map.has_key?(seen, cursor) or map_size(seen) >= 100,
         {:ok, body} <- HTTP.call(provider, credentials, :get, path, params: params),
         {:ok, page} <- normalize_page(body[collection], normalize),
         {:ok, next} <- next_params(body, provider, path, params, collection) do
      continue(next, provider, credentials, path, collection, normalize, Map.put(seen, cursor, true), records ++ page)
    else
      true -> {:error, :invalid_response}
      {:error, reason} -> {:error, reason}
    end
  end

  defp continue(nil, _provider, _credentials, _path, _collection, _normalize, _seen, records), do: {:ok, records}

  defp continue(params, provider, credentials, path, collection, normalize, seen, records),
    do: walk(provider, credentials, path, params, collection, normalize, seen, records)

  defp normalize_page(rows, normalize) when is_list(rows) and length(rows) <= 1000 do
    rows
    |> Enum.reduce_while({:ok, []}, fn row, {:ok, acc} ->
      case normalize.(row) do
        {:ok, record} -> {:cont, {:ok, [record | acc]}}
        {:error, _reason} -> {:halt, {:error, :invalid_response}}
      end
    end)
    |> reverse_page()
  end

  defp normalize_page(_rows, _normalize), do: {:error, :invalid_response}
  defp reverse_page({:ok, rows}), do: {:ok, Enum.reverse(rows)}
  defp reverse_page(error), do: error

  defp next_params(%{"next_page_uri" => next}, :twilio, path, params, _collection),
    do: parse_next(next, :twilio, path, params)

  defp next_params(%{"links" => %{"next" => next}}, :vantage, path, params, _collection),
    do: parse_next(next, :vantage, path, params)

  defp next_params(body, :vantage, _path, _params, "workspaces") when not is_map_key(body, "links"), do: {:ok, nil}
  defp next_params(_body, _provider, _path, _params, _collection), do: {:error, :invalid_response}

  defp parse_next(nil, _provider, _path, _params), do: {:ok, nil}

  defp parse_next(link, provider, path, params) when is_binary(link) do
    expected = URI.parse(HTTP.origin(provider) <> path)
    uri = URI.merge(expected, link)

    case {uri.scheme, uri.host, uri.port, uri.path, uri.userinfo, uri.fragment, uri.query} do
      {"https", host, 443, ^path, nil, nil, query} when host == expected.host and is_binary(query) ->
        validate_query(URI.decode_query(query), provider, params)

      _other ->
        {:error, :invalid_response}
    end
  rescue
    _exception -> {:error, :invalid_response}
  end

  defp parse_next(_link, _provider, _path, _params), do: {:error, :invalid_response}

  defp validate_query(query, :twilio, _params) do
    case Map.keys(query) -- ["Page", "PageToken", "PageSize"] do
      [] -> {:ok, Map.to_list(query)}
      _other -> {:error, :invalid_response}
    end
  end

  defp validate_query(query, :vantage, params) do
    expected_provider = params |> Map.new(fn {key, value} -> {to_string(key), value} end) |> Map.get("provider")

    case {Map.keys(query) -- ["page", "limit", "provider"], query["provider"] == expected_provider} do
      {[], true} -> {:ok, Map.to_list(query)}
      _other -> {:error, :invalid_response}
    end
  end
end
