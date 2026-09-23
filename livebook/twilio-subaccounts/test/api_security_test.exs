defmodule TwilioOnboarding.APISecurityTest do
  use ExUnit.Case, async: false

  import ExUnit.CaptureLog

  alias TwilioOnboarding.API.Discovery
  alias TwilioOnboarding.API.HTTP
  alias TwilioOnboarding.API.Twilio
  alias TwilioOnboarding.API.Vantage
  alias TwilioOnboarding.Credentials
  alias TwilioOnboarding.Key

  @parent "AC00000000000000000000000000000001"
  @child "AC00000000000000000000000000000002"
  @key "SK00000000000000000000000000000001"
  @integration "accss_crdntl_0000000000000001"
  @workspace "wrkspc_0000000000000001"
  @auth_token "parent-auth-token-canary-12345678"
  @vantage_token "vantage-api-token-canary-12345678"
  @key_secret "child-key-secret-canary-12345678"

  setup do
    previous = Req.default_options()
    Req.default_options(plug: {Req.Test, __MODULE__})
    Req.Test.verify_on_exit!()
    on_exit(fn -> Req.default_options(previous) end)
    temp = if File.dir?("/private/tmp"), do: "/private/tmp", else: "/tmp"
    root = Path.join(temp, "twilio-discovery-test-" <> Base.encode16(:crypto.strong_rand_bytes(8)))
    Process.put(:state_root, root)
    on_exit(fn -> File.rm_rf!(root) end)
    :ok
  end

  test "each provider receives only its intended authentication on a fixed HTTPS origin" do
    twilio_auth = "Basic " <> Base.encode64(@parent <> ":" <> @auth_token)

    for {provider, host, auth} <- [
          {:twilio, "api.twilio.com", twilio_auth},
          {:twilio_iam, "iam.twilio.com", twilio_auth},
          {:vantage, "api.vantage.sh", "Bearer " <> @vantage_token}
        ] do
      Req.Test.expect(__MODULE__, fn conn ->
        assert {conn.scheme, conn.host, conn.port, conn.request_path} == {:https, host, 443, "/probe"}
        assert Plug.Conn.get_req_header(conn, "authorization") == [auth]
        Req.Test.json(conn, %{"ok" => true})
      end)

      assert HTTP.call(provider, credentials(), :get, "/probe", url: "https://attacker.example", auth: {:bearer, "wrong"}) ==
               {:ok, %{"ok" => true}}
    end
  end

  test "unsafe request paths fail before a request is sent" do
    test_pid = self()

    Req.Test.stub(__MODULE__, fn conn ->
      send(test_pid, :unexpected_request)
      Req.Test.json(conn, %{})
    end)

    for path <- [
          "https://attacker.example",
          "//attacker.example",
          "/probe?secret=leak",
          "/probe#fragment",
          "/probe\\other",
          "/probe\n"
        ] do
      assert HTTP.call(:twilio, credentials(), :get, path) == {:error, :invalid_response}
    end

    refute_received :unexpected_request
  end

  test "redirect responses are never followed for reads or writes" do
    test_pid = self()

    for {method, reason} <- [get: :unavailable, post: :uncertain] do
      Req.Test.stub(__MODULE__, fn conn ->
        send(test_pid, {:redirect_request, conn.host})
        conn |> Plug.Conn.put_resp_header("location", "https://attacker.example/collect") |> Plug.Conn.send_resp(302, "")
      end)

      assert HTTP.call(:twilio, credentials(), method, "/probe") == {:error, reason}
      assert_received {:redirect_request, "api.twilio.com"}
      refute_received {:redirect_request, _}
    end
  end

  test "429 retries stop after three attempts and never retry a server failure" do
    Req.Test.expect(__MODULE__, 3, &Plug.Conn.send_resp(&1, 429, "rate-limit-body-canary"))
    assert HTTP.call(:vantage, credentials(), :get, "/probe") == {:error, :rate_limited}

    test_pid = self()

    Req.Test.stub(__MODULE__, fn conn ->
      send(test_pid, :server_request)
      Plug.Conn.send_resp(conn, 500, "server-body-canary")
    end)

    assert HTTP.call(:vantage, credentials(), :post, "/probe") == {:error, :uncertain}
    assert_received :server_request
    refute_received :server_request
  end

  test "malformed successful mutation responses remain uncertain" do
    for body <- ["invalid-json-secret", "[]", "null"] do
      Req.Test.expect(__MODULE__, &Plug.Conn.send_resp(&1, 201, body))
      assert HTTP.call(:vantage, credentials(), :post, "/probe") == {:error, :uncertain}
    end

    Req.Test.expect(__MODULE__, &Req.Test.json(&1, %{"sid" => @key}))
    assert Twilio.create_key(credentials(), @child, "run-id") == {:error, :uncertain}

    Req.Test.expect(__MODULE__, &Req.Test.json(&1, integration(@parent)))
    assert Vantage.create_integration(credentials(), entry(), key()) == {:error, :uncertain}
  end

  test "oversized responses are stopped without reflecting body contents" do
    Req.Test.expect(__MODULE__, &Plug.Conn.send_resp(&1, 200, String.duplicate("x", 4_194_305)))
    assert HTTP.call(:vantage, credentials(), :get, "/probe") == {:error, :unavailable}
  end

  test "safe errors and logs exclude secrets and raw provider errors" do
    logs =
      capture_log(fn ->
        for {status, reason} <- [{401, :unauthorized}, {403, :forbidden}, {422, :rejected}, {503, :uncertain}] do
          Req.Test.expect(__MODULE__, &Plug.Conn.send_resp(&1, status, @auth_token <> @vantage_token <> @key_secret))
          assert HTTP.call(:vantage, credentials(), :post, "/probe") == {:error, reason}
        end

        Req.Test.expect(__MODULE__, &Req.Test.transport_error(&1, :timeout))
        assert HTTP.call(:twilio, credentials(), :post, "/probe") == {:error, :uncertain}
      end)

    for secret <- [@auth_token, @vantage_token, @key_secret], do: refute(logs =~ secret)
  end

  test "Twilio inventory traverses pages and removes raw authentication fields" do
    Req.Test.expect(__MODULE__, fn conn ->
      assert Plug.Conn.fetch_query_params(conn).query_params == %{"PageSize" => "1000"}

      Req.Test.json(conn, %{
        "accounts" => [account(@parent, @parent)],
        "next_page_uri" => "/2010-04-01/Accounts.json?PageToken=next&PageSize=1000"
      })
    end)

    Req.Test.expect(__MODULE__, fn conn ->
      assert Plug.Conn.fetch_query_params(conn).query_params == %{"PageSize" => "1000", "PageToken" => "next"}
      Req.Test.json(conn, %{"accounts" => [account(@child, @parent)], "next_page_uri" => nil})
    end)

    assert Twilio.list_accounts(credentials()) ==
             {:ok, [normalized_account(@parent, @parent), normalized_account(@child, @parent)]}
  end

  test "Vantage inventory reads every page and retains only normalized identity" do
    Req.Test.expect(__MODULE__, fn conn ->
      assert Plug.Conn.fetch_query_params(conn).query_params == %{"provider" => "twilio", "limit" => "1000"}

      Req.Test.json(conn, %{
        "integrations" => [integration(@child)],
        "links" => %{"next" => "https://api.vantage.sh/v2/integrations?page=2&provider=twilio&limit=1000"}
      })
    end)

    Req.Test.expect(__MODULE__, fn conn ->
      assert Plug.Conn.fetch_query_params(conn).query_params == %{
               "page" => "2",
               "provider" => "twilio",
               "limit" => "1000"
             }

      row =
        @parent
        |> integration()
        |> Map.put("token", "accss_crdntl_0000000000000002")
        |> Map.put("api_secret", @key_secret)

      Req.Test.json(conn, %{"integrations" => [row], "links" => %{"next" => nil}})
    end)

    assert Vantage.list_integrations(credentials()) ==
             {:ok,
              [
                %{
                  token: @integration,
                  account_sid: nil,
                  identity_hint: @child,
                  identity_label: @child,
                  status: "importing"
                },
                %{
                  token: "accss_crdntl_0000000000000002",
                  account_sid: nil,
                  identity_hint: @parent,
                  identity_label: @parent,
                  status: "importing"
                }
              ]}
  end

  test "foreign origins, changed resources, and altered provider filters cannot control pagination" do
    for link <- [
          "https://attacker.example/v2/integrations?page=2&provider=twilio",
          "//attacker.example/v2/integrations?page=2&provider=twilio",
          "https://api.vantage.sh@attacker.example/v2/integrations?page=2&provider=twilio",
          "http://api.vantage.sh/v2/integrations?page=2&provider=twilio",
          "/v2/workspaces?page=2&provider=twilio",
          "/v2/integrations?page=2&provider=aws",
          "/v2/integrations?page=2&provider=twilio&auth=leak",
          "/v2/integrations?page=2&provider=twilio#fragment"
        ] do
      Req.Test.expect(__MODULE__, &Req.Test.json(&1, %{"integrations" => [], "links" => %{"next" => link}}))
      assert Vantage.list_integrations(credentials()) == {:error, :invalid_response}
    end
  end

  test "reordered query parameters cannot disguise a pagination loop" do
    test_pid = self()

    Req.Test.stub(__MODULE__, fn conn ->
      send(test_pid, :pagination_request)
      Req.Test.json(conn, %{"integrations" => [], "links" => %{"next" => "/v2/integrations?limit=1000&provider=twilio"}})
    end)

    assert Vantage.list_integrations(credentials()) == {:error, :invalid_response}
    assert_received :pagination_request
    refute_received :pagination_request
  end

  test "Twilio pagination rejects foreign links and unrecognized query parameters" do
    for link <- [
          "https://attacker.example/2010-04-01/Accounts.json?Page=2",
          "/2010-04-01/Accounts.json?AccountSid=" <> @child
        ] do
      Req.Test.expect(__MODULE__, &Req.Test.json(&1, %{"accounts" => [], "next_page_uri" => link}))
      assert Twilio.list_accounts(credentials()) == {:error, :invalid_response}
    end
  end

  test "workspaces support the API's unpaginated response without links" do
    Req.Test.expect(__MODULE__, &Req.Test.json(&1, %{"workspaces" => [workspace()]}))
    assert Vantage.list_workspaces(credentials()) == {:ok, [%{token: @workspace, name: "Finance"}]}
  end

  test "discovery validates the active parent before contacting Vantage" do
    for parent <- [
          account(@child, @parent),
          account(@parent, @child),
          Map.put(account(@parent, @parent), "status", "suspended")
        ] do
      Req.Test.expect(__MODULE__, fn conn ->
        assert conn.host == "api.twilio.com"
        Req.Test.json(conn, %{"accounts" => [parent], "next_page_uri" => nil})
      end)

      assert Discovery.load(credentials(), state_root: Process.get(:state_root)) == {:error, :invalid_parent}
    end
  end

  test "successful read-only discovery does not imply write authorization" do
    expect_discovery([workspace()])

    assert {:ok, %{accounts: [_], integrations: [], workspaces: [_]}} =
             Discovery.load(credentials(), state_root: Process.get(:state_root))

    Req.Test.expect(__MODULE__, fn conn ->
      assert {conn.host, conn.method} == {"api.vantage.sh", "POST"}
      Plug.Conn.send_resp(conn, 403, "insufficient-permission-canary")
    end)

    assert Vantage.create_integration(credentials(), entry(), key()) == {:error, :forbidden}
  end

  test "discovery refuses an account with no available workspace" do
    expect_discovery([])
    assert Discovery.load(credentials(), state_root: Process.get(:state_root)) == {:error, :no_workspaces}
  end

  test "integration payload contains the selected child's key, never parent credentials" do
    Req.Test.expect(__MODULE__, fn conn ->
      {:ok, body, conn} = Plug.Conn.read_body(conn)

      assert Jason.decode!(body) == %{
               "api_key" => @key,
               "api_secret" => @key_secret,
               "account_sid" => @child,
               "friendly_account_name" => "Customer",
               "description" => "Twilio sub-account " <> @child
             }

      Req.Test.json(conn, integration(@child))
    end)

    assert Vantage.create_integration(credentials(), entry(), key()) ==
             {:ok,
              %{
                token: @integration,
                account_sid: @child,
                identity_hint: @child,
                identity_label: @child,
                status: "importing"
              }}
  end

  test "key creation and workspace assignment send only their allowlisted parameters" do
    Req.Test.expect(__MODULE__, fn conn ->
      assert {conn.host, conn.request_path, conn.method} == {"iam.twilio.com", "/v1/Keys", "POST"}
      {:ok, body, conn} = Plug.Conn.read_body(conn)
      assert URI.decode_query(body) == %{"AccountSid" => @child, "FriendlyName" => "vantage-run-id"}
      Req.Test.json(conn, %{"sid" => @key, "secret" => @key_secret, "auth_token" => @auth_token})
    end)

    assert Twilio.create_key(credentials(), @child, "run-id") == {:ok, key()}

    Req.Test.expect(__MODULE__, fn conn ->
      assert {conn.host, conn.request_path, conn.method} == {"api.vantage.sh", "/v2/integrations/" <> @integration, "PUT"}
      {:ok, body, conn} = Plug.Conn.read_body(conn)
      assert Jason.decode!(body) == %{"workspace_tokens" => [@workspace]}
      Req.Test.json(conn, %{})
    end)

    assert Vantage.assign_workspace(credentials(), @integration, @workspace) == :ok
  end

  test "credential and child-key inspection redact their secret fields" do
    output = inspect(%{credentials: credentials(), key: key()})
    assert output =~ @parent
    assert output =~ @key
    for secret <- [@auth_token, @vantage_token, @key_secret], do: refute(output =~ secret)
  end

  defp credentials, do: %Credentials{parent_sid: @parent, auth_token: @auth_token, vantage_token: @vantage_token}
  defp key, do: %Key{sid: @key, secret: @key_secret}
  defp entry, do: %{sid: @child, name: "Customer", action: :connect, integration_token: nil}
  defp workspace, do: %{"token" => @workspace, "name" => "Finance"}
  defp integration(sid), do: %{"token" => @integration, "account_identifier" => sid, "status" => "importing"}

  defp account(sid, owner),
    do: %{
      "sid" => sid,
      "owner_account_sid" => owner,
      "friendly_name" => "Customer",
      "status" => "active",
      "auth_token" => @auth_token
    }

  defp normalized_account(sid, owner), do: %{sid: sid, parent_sid: owner, name: "Customer", status: "active"}

  defp expect_discovery(workspaces) do
    Req.Test.expect(__MODULE__, fn conn ->
      assert {conn.host, conn.method} == {"api.twilio.com", "GET"}
      Req.Test.json(conn, %{"accounts" => [account(@parent, @parent)], "next_page_uri" => nil})
    end)

    Req.Test.expect(__MODULE__, fn conn ->
      assert {conn.request_path, conn.method} == {"/v2/integrations", "GET"}
      Req.Test.json(conn, %{"integrations" => [], "links" => %{"next" => nil}})
    end)

    Req.Test.expect(__MODULE__, fn conn ->
      assert {conn.request_path, conn.method} == {"/v2/workspaces", "GET"}
      Req.Test.json(conn, %{"workspaces" => workspaces})
    end)
  end
end
