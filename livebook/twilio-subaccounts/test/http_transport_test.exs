defmodule TwilioOnboarding.HTTPTransportTest do
  use ExUnit.Case, async: false

  alias TwilioOnboarding.API.HTTP
  alias TwilioOnboarding.Credentials

  defmodule LoopbackAdapter do
    @moduledoc false

    @doc false
    @spec run(Req.Request.t()) :: {Req.Request.t(), Req.Response.t() | Exception.t()}
    def run(request) do
      %{port: port, cacerts: cacerts} = Process.get(:loopback_target)
      finch = Map.get(request.options, :finch, [])
      connection = Keyword.get(finch, :conn_opts, [])
      transport = Keyword.get(connection, :transport_opts, [])
      transport = Keyword.put(transport, :cacerts, cacerts)
      connection = Keyword.put(connection, :transport_opts, transport)
      options = Map.put(request.options, :finch, Keyword.put(finch, :conn_opts, connection))
      url = %{request.url | host: "localhost", port: port}
      Req.Finch.run(%{request | url: url, options: options})
    end
  end

  setup_all do
    san = {:Extension, {2, 5, 29, 17}, false, [{:dNSName, ~c"localhost"}]}
    key_options = [key: {:rsa, 2048, 65_537}, digest: :sha256]
    certificates = :public_key.pkix_test_data(%{root: key_options, peer: key_options ++ [extensions: [san]]})
    %{certificates: certificates}
  end

  setup do
    previous = Req.default_options()
    Req.default_options(adapter: LoopbackAdapter)
    on_exit(fn -> Req.default_options(previous) end)
    :ok
  end

  test "the production Finch options complete a verified TLS request", test do
    start_server(test.certificates, {:response, ~s({"ok":true})})
    assert HTTP.call(:twilio, credentials(), :get, "/probe") == {:ok, %{"ok" => true}}
    assert_receive :tls_request_received
  end

  test "an untrusted TLS certificate is rejected", test do
    start_server(test.certificates, {:response, ~s({"ok":true})}, [])
    assert HTTP.call(:twilio, credentials(), :get, "/probe") == {:error, :unavailable}
    assert_receive :tls_handshake_rejected
  end

  test "a lost write response remains uncertain after a real TLS request", test do
    start_server(test.certificates, :close)
    assert HTTP.call(:vantage, credentials(), :post, "/probe", json: %{account: "fake"}) == {:error, :uncertain}
    assert_receive :tls_request_received
  end

  test "a streamed response above the body limit is rejected", test do
    body = Jason.encode!(%{data: String.duplicate("x", 4_194_304)})
    start_server(test.certificates, {:response, body})
    assert HTTP.call(:twilio, credentials(), :get, "/probe") == {:error, :unavailable}
    assert_receive :tls_request_received
  end

  defp start_server(certificates, response, trusted_certificates \\ nil) do
    options = [:binary, active: false, ip: {127, 0, 0, 1}] ++ certificates
    {:ok, listener} = :ssl.listen(0, options)
    {:ok, {_address, port}} = :ssl.sockname(listener)
    cacerts = trusted_certificates || Keyword.fetch!(certificates, :cacerts)
    Process.put(:loopback_target, %{port: port, cacerts: cacerts})
    observer = self()
    server = spawn(fn -> serve(listener, response, observer) end)

    on_exit(fn ->
      :ssl.close(listener)
      if Process.alive?(server), do: Process.exit(server, :kill)
    end)
  end

  defp serve(listener, response, observer) do
    with {:ok, socket} <- :ssl.transport_accept(listener, 5_000),
         {:ok, connection} <- :ssl.handshake(socket, 5_000) do
      case :ssl.recv(connection, 0, 5_000) do
        {:ok, _request} ->
          send(observer, :tls_request_received)
          respond(connection, response)

        _error ->
          :ok
      end

      :ssl.close(connection)
    else
      {:error, _reason} -> send(observer, :tls_handshake_rejected)
    end
  end

  defp respond(_connection, :close), do: :ok

  defp respond(connection, {:response, body}) do
    :ssl.send(connection, [
      "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: ",
      Integer.to_string(byte_size(body)),
      "\r\n\r\n",
      body
    ])
  end

  defp credentials do
    {:ok, credentials} =
      Credentials.new("AC" <> String.duplicate("1", 32), "fake-parent-auth-token", "fake-vantage-api-token")

    credentials
  end
end
