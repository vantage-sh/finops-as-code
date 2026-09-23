defmodule TwilioOnboarding.ExecutionTest do
  use ExUnit.Case, async: true

  alias TwilioOnboarding.Core.Identity
  alias TwilioOnboarding.Core.Plan
  alias TwilioOnboarding.Credentials
  alias TwilioOnboarding.Execution
  alias TwilioOnboarding.Journal

  @parent "AC00000000000000000000000000000000"
  @child "AC11111111111111111111111111111111"
  @workspace "wrkspc_1111111111111111"
  @integration "accss_crdntl_1111111111111111"
  @key "SK11111111111111111111111111111111"

  defmodule FakeTwilio do
    @moduledoc false

    @doc false
    @spec list_accounts(term()) :: {:ok, [map()]}
    def list_accounts(_credentials), do: {:ok, Process.get(:accounts)}

    @doc false
    @spec get_account(term(), String.t()) :: {:ok, map()} | {:error, atom()}
    def get_account(_credentials, sid) do
      Process.get(:get_account, {:ok, Enum.find(Process.get(:accounts), &(&1.sid == sid))})
    end

    @doc false
    @spec create_key(term(), String.t(), String.t()) :: term()
    def create_key(_credentials, sid, _run_id),
      do: call(:create_key, sid, {:ok, %{sid: "SK11111111111111111111111111111111", secret: "private-key-secret"}})

    @doc false
    @spec delete_key(term(), String.t(), String.t()) :: term()
    def delete_key(_credentials, sid, key), do: call(:delete_key, {sid, key}, :ok)

    defp call(action, value, default) do
      Process.put(:calls, Process.get(:calls, []) ++ [{action, value}])

      case Process.get(action, default) do
        callback when is_function(callback, 0) -> callback.()
        response -> response
      end
    end
  end

  defmodule FakeVantage do
    @moduledoc false

    alias TwilioOnboarding.Core.Inventory

    @doc false
    @spec list_integrations(term()) :: {:ok, [map()]}
    def list_integrations(_credentials) do
      integrations =
        Enum.map(Process.get(:integrations, []), fn row ->
          {:ok, normalized} =
            Inventory.integration(%{
              "token" => row.token,
              "status" => row.status,
              "account_identifier" => Map.get(row, :identity_label, row.account_sid)
            })

          normalized
        end)

      {:ok, integrations}
    end

    @doc false
    @spec create_integration(term(), map(), term()) :: term()
    def create_integration(_credentials, entry, _key) do
      Process.put(:calls, Process.get(:calls, []) ++ [{:create_integration, entry.sid}])
      integration = %{token: "accss_crdntl_1111111111111111", account_sid: entry.sid, status: "pending"}

      case Process.get(:create_integration) do
        nil ->
          Process.put(:integrations, [integration])
          {:ok, integration}

        :committed_timeout ->
          Process.put(:integrations, [integration])
          {:error, :uncertain}

        response ->
          response
      end
    end

    @doc false
    @spec assign_workspace(term(), String.t(), String.t()) :: term()
    def assign_workspace(_credentials, token, workspace) do
      Process.put(:calls, Process.get(:calls, []) ++ [{:assign_workspace, {token, workspace}}])
      Process.get(:assign_workspace, :ok)
    end
  end

  setup do
    temp = if File.dir?("/private/tmp"), do: "/private/tmp", else: "/tmp"
    root = Path.join(temp, "twilio-execution-test-" <> Base.encode16(:crypto.strong_rand_bytes(8)))
    on_exit(fn -> File.rm_rf!(root) end)
    account = %{sid: @child, parent_sid: @parent, name: "Customer private name", status: "active"}
    Process.put(:accounts, [account])
    Process.put(:calls, [])
    {:ok, plan} = Plan.build(@parent, [account], [], [@child], @workspace)
    {:ok, credentials} = Credentials.new(@parent, "private-parent-token", "private-vantage-token")

    %{
      root: root,
      plan: plan,
      credentials: credentials,
      options: [state_root: root, twilio: FakeTwilio, vantage: FakeVantage]
    }
  end

  test "persists intent before a key is created and completes one connection", test do
    Process.put(:create_key, fn ->
      records = checkpoints(test.root)
      assert List.last(records)["outcome"] == "key_pending"
      {:ok, %{sid: @key, secret: "private-key-secret"}}
    end)

    assert {:ok, [%{status: :connected, integration_token: @integration}]} = run(test)

    assert Process.get(:calls) == [
             create_key: @child,
             create_integration: @child,
             assign_workspace: {@integration, @workspace}
           ]

    assert List.last(checkpoints(test.root))["outcome"] == "complete"
  end

  test "a completed rerun never creates or assigns again", test do
    assert {:ok, _} = run(test)
    Process.put(:calls, [])
    assert {:ok, [%{status: :connected}]} = run(test)
    assert Process.get(:calls) == []
  end

  test "an uncertain key creation is never repeated on restart", test do
    Process.put(:create_key, {:error, :uncertain})
    assert {:ok, [%{status: :needs_attention}]} = run(test)
    Process.put(:calls, [])
    Process.delete(:create_key)
    assert {:ok, [%{status: :needs_attention, reason: :outcome_unknown}]} = run(test)
    assert Process.get(:calls) == []
  end

  test "an uncertain response retains a matching integration for review without mutating it", test do
    Process.put(:create_integration, :committed_timeout)
    assert {:ok, [%{status: :needs_attention, reason: :outcome_unknown}]} = run(test)
    refute Enum.any?(Process.get(:calls), &match?({:delete_key, _}, &1))
    refute Enum.any?(Process.get(:calls), &match?({:assign_workspace, _}, &1))
    Process.put(:calls, [])
    assert {:error, :unidentified_integration} = run(test)
    test = confirm(test, @child)
    assert {:ok, [%{status: :needs_attention, reason: :integration_found_needs_review}]} = run(test)
    assert Process.get(:calls) == []
  end

  test "an unresolved integration timeout preserves the key and cannot duplicate creation", test do
    Process.put(:create_integration, {:error, :uncertain})
    assert {:ok, [%{status: :needs_attention}]} = run(test)
    refute Enum.any?(Process.get(:calls), &match?({:delete_key, _}, &1))
    Process.put(:calls, [])
    assert {:ok, [%{status: :needs_attention}]} = run(test)
    assert Process.get(:calls) == []
  end

  test "a definitive rejection cleans up only the key just created", test do
    Process.put(:create_integration, {:error, :name_conflict})
    assert {:ok, [%{status: :failed, reason: :name_conflict}]} = run(test)
    assert List.last(Process.get(:calls)) == {:delete_key, {@child, @key}}
    Process.put(:calls, [])
    assert {:ok, [%{status: :failed}]} = run(test)
    assert Process.get(:calls) == []
  end

  test "failed cleanup is retained for manual review", test do
    Process.put(:create_integration, {:error, :rejected})
    Process.put(:delete_key, {:error, :uncertain})
    assert {:ok, [%{status: :needs_attention, reason: :cleanup_failed}]} = run(test)
    assert List.last(checkpoints(test.root))["outcome"] == "cleanup_failed"
  end

  test "workspace assignment resumes without creating a second integration or key", test do
    Process.put(:assign_workspace, {:error, :forbidden})
    assert {:ok, [%{status: :workspace_pending}]} = run(test)
    Process.put(:calls, [])
    Process.delete(:assign_workspace)
    assert {:ok, [%{status: :connected}]} = run(test)
    assert Process.get(:calls) == [assign_workspace: {@integration, @workspace}]
  end

  test "a new unidentified connection appearing after preview blocks mutation", test do
    Process.put(:integrations, [%{token: @integration, account_sid: @child, status: "connected"}])
    assert {:error, :unidentified_integration} = run(test)
    assert Process.get(:calls) == []
  end

  test "a confirmed existing child is skipped after rechecking its relationship", test do
    Process.put(:integrations, [%{token: @integration, account_sid: @child, status: "connected"}])
    assert {:ok, [%{status: :skipped}]} = test |> confirm(@child) |> run()
    assert Process.get(:calls) == []
  end

  test "confirmation cannot survive changed connection metadata", test do
    Process.put(:integrations, [%{token: @integration, account_sid: @child, status: "connected"}])
    test = confirm(test, @child)

    Process.put(:integrations, [
      %{token: @integration, account_sid: @child, identity_label: "Changed connection", status: "connected"}
    ])

    assert {:error, :plan_changed} = run(test)
    assert Process.get(:calls) == []
  end

  test "unreachable or mismatched Twilio identity fails before mutation", test do
    Process.put(:integrations, [%{token: @integration, account_sid: @child, status: "connected"}])
    test = confirm(test, @child)
    Process.put(:get_account, {:error, :forbidden})
    assert {:error, :forbidden} = run(test)
    Process.put(:get_account, {:ok, %{hd(Process.get(:accounts)) | parent_sid: @child}})
    assert {:error, :plan_changed} = run(test)
    assert Process.get(:calls) == []
  end

  test "confirming a parent blocks overlapping child connections", test do
    parent = %{sid: @parent, parent_sid: @parent, status: "active", name: "Parent"}
    Process.put(:accounts, [parent | Process.get(:accounts)])
    Process.put(:integrations, [%{token: @integration, account_sid: @parent, status: "connected"}])
    assert {:error, :parent_already_connected} = test |> confirm(@parent) |> run()
    assert Process.get(:calls) == []
  end

  test "a completed journal restores identity without relying on the connection description", test do
    assert {:ok, _} = run(test)
    Process.put(:calls, [])

    Process.put(:integrations, [
      %{token: @integration, account_sid: nil, identity_label: "Customer connection", status: "connected"}
    ])

    assert {:ok, [%{status: :connected}]} = run(test)
    assert Process.get(:calls) == []
  end

  test "inventory is refreshed before each creation in a batch", test do
    second = %{hd(Process.get(:accounts)) | sid: "AC22222222222222222222222222222222"}
    accounts = Process.get(:accounts) ++ [second]
    Process.put(:accounts, accounts)
    {:ok, plan} = Plan.build(@parent, accounts, [], [@child, second.sid], @workspace)

    progress = fn _ ->
      unknown = %{token: "accss_crdntl_2222222222222222", account_sid: nil, status: "pending"}
      Process.put(:integrations, Process.get(:integrations) ++ [unknown])
    end

    assert {:error, :unidentified_integration} = Execution.run(plan, test.credentials, progress, test.options)

    assert Process.get(:calls) == [
             create_key: @child,
             create_integration: @child,
             assign_workspace: {@integration, @workspace}
           ]
  end

  test "identity discovery reads saved records without changing destination or credential checks", test do
    assert {:ok, _} = run(test)
    context = %{parent_sid: @parent, fingerprint: Credentials.fingerprint(test.credentials)}
    assert {:ok, records} = Journal.records(context, test.options)
    assert records[@child].integration_token == @integration
    assert {:error, :credentials_changed} = Journal.records(%{context | fingerprint: "different"}, test.options)
    assert {:error, :destination_changed} = run(%{test | plan: %{test.plan | workspace_token: "wrkspc_2222222222222222"}})
  end

  test "a parent mismatch and suspended child block all mutations", test do
    credentials = %{test.credentials | parent_sid: "AC22222222222222222222222222222222"}
    assert {:error, :invalid_destination} = run(%{test | credentials: credentials})
    Process.put(:accounts, [%{hd(Process.get(:accounts)) | status: "suspended"}])
    assert {:error, :invalid_selection} = run(test)
    assert Process.get(:calls) == []
  end

  test "unidentified integrations block creation before keys are minted", test do
    Process.put(:integrations, [%{token: @integration, account_sid: nil, status: "connected"}])
    assert {:error, :unidentified_integration} = run(test)
    assert Process.get(:calls) == []
  end

  test "the journal excludes names and all credentials and uses private permissions", test do
    assert {:ok, _} = run(test)
    [path] = Path.wildcard(Path.join(test.root, "*/journal.jsonl"))
    content = File.read!(path)

    Enum.each(
      ["Customer private name", "private-parent-token", "private-vantage-token", "private-key-secret"],
      fn value ->
        refute String.contains?(content, value)
      end
    )

    assert Bitwise.band(File.stat!(path).mode, 0o777) == 0o600
    assert Bitwise.band(File.stat!(Path.dirname(path)).mode, 0o777) == 0o700
  end

  test "changed destination credentials cannot abandon unfinished recovery", test do
    Process.put(:create_key, {:error, :uncertain})
    assert {:ok, _} = run(test)
    credentials = %{test.credentials | vantage_token: "replacement-vantage-token"}
    assert {:error, :credentials_changed} = run(%{test | credentials: credentials})
  end

  test "changing workspace cannot abandon unfinished recovery", test do
    Process.put(:create_key, {:error, :uncertain})
    assert {:ok, _} = run(test)
    Process.put(:calls, [])
    plan = %{test.plan | workspace_token: "wrkspc_2222222222222222"}
    assert {:error, :destination_changed} = run(%{test | plan: plan})
    assert Process.get(:calls) == []
  end

  test "a truncated checkpoint fails closed", test do
    assert {:ok, _} = run(test)
    [path] = Path.wildcard(Path.join(test.root, "*/journal.jsonl"))
    File.write!(path, "{", [:append])
    Process.put(:calls, [])
    assert {:error, :journal_invalid} = run(test)
    assert Process.get(:calls) == []
  end

  test "an invalid header fails closed without raising", test do
    assert {:ok, _} = run(test)
    [path] = Path.wildcard(Path.join(test.root, "*/journal.jsonl"))
    File.write!(path, "[]\n")
    Process.put(:calls, [])
    assert {:error, :journal_invalid} = run(test)
    assert Process.get(:calls) == []
  end

  test "a skip action without a known integration cannot authorize creation", test do
    plan = %{test.plan | entries: [%{hd(test.plan.entries) | action: :skip}]}
    assert {:error, :plan_changed} = run(%{test | plan: plan})
    assert Process.get(:calls) == []
  end

  test "a second runtime cannot enter an active parent run even for another workspace", test do
    fingerprint = Credentials.fingerprint(test.credentials)
    context = %{parent_sid: @parent, workspace_token: @workspace, fingerprint: fingerprint}

    assert {:error, :run_locked} =
             Journal.with_lock(context, test.options, fn _ ->
               plan = %{test.plan | workspace_token: "wrkspc_2222222222222222"}
               run(%{test | plan: plan})
             end)

    assert Process.get(:calls) == []
  end

  test "a symlink recovery directory is rejected without following it", test do
    target = test.root <> "-target"
    File.mkdir!(target)
    on_exit(fn -> File.rm_rf!(target) end)
    File.ln_s!(target, test.root)
    assert {:error, :journal_unavailable} = run(test)
    assert File.ls!(target) == []
    assert Process.get(:calls) == []
  end

  test "an unsuccessful preflight does not bind a future run to its workspace", test do
    account = hd(Process.get(:accounts))
    Process.put(:accounts, [%{account | status: "suspended"}])
    assert {:error, :invalid_selection} = run(test)
    Process.put(:accounts, [account])
    plan = %{test.plan | workspace_token: "wrkspc_2222222222222222"}
    assert {:ok, [%{status: :connected}]} = run(%{test | plan: plan})
  end

  test "a lost key secret never causes a replacement key to be minted", test do
    checkpoint(test, "key_created", @key, nil)
    assert {:ok, [%{status: :needs_attention, reason: :outcome_unknown}]} = run(test)
    assert Process.get(:calls) == []
  end

  test "a confirmed integration survives restart and resumes workspace assignment", test do
    checkpoint(test, "integration_created", @key, @integration)
    Process.put(:integrations, [%{token: @integration, account_sid: @child, status: "pending"}])
    assert {:ok, [%{status: :connected}]} = run(test)
    assert Process.get(:calls) == [assign_workspace: {@integration, @workspace}]
  end

  test "a removed integration is never silently recreated from a completed record", test do
    assert {:ok, _} = run(test)
    Process.put(:integrations, [])
    Process.put(:calls, [])
    assert {:ok, [%{status: :needs_attention, reason: :integration_missing}]} = run(test)
    assert Process.get(:calls) == []
  end

  test "a stale process lock fails closed", test do
    File.mkdir_p!(test.root)
    lock = :sha256 |> :crypto.hash(@parent) |> Base.encode16(case: :lower)
    File.mkdir!(Path.join(test.root, lock <> ".lock"))
    assert {:error, :run_locked} = run(test)
    assert Process.get(:calls) == []
  end

  test "a recovery file symlink cannot replace the saved checkpoints", test do
    assert {:ok, _} = run(test)
    [path] = Path.wildcard(Path.join(test.root, "*/journal.jsonl"))
    saved = path <> ".saved"
    File.rename!(path, saved)
    File.ln_s!(saved, path)
    Process.put(:calls, [])
    assert {:error, :journal_invalid} = run(test)
    assert Process.get(:calls) == []
  end

  test "raw exceptions cannot appear in results or the journal", test do
    Process.put(:create_key, fn -> raise "private-parent-token" end)
    assert {:ok, [%{status: :needs_attention, reason: :outcome_unknown}]} = run(test)
    refute inspect(checkpoints(test.root)) =~ "private-parent-token"
  end

  defp run(test), do: Execution.run(test.plan, test.credentials, fn _ -> :ok end, test.options)

  defp confirm(test, sid) do
    {:ok, integrations} = FakeVantage.list_integrations(test.credentials)
    account = Enum.find(Process.get(:accounts), &(&1.sid == sid))
    {:ok, evidence} = Identity.confirm(integrations, @integration, account)
    %{test | plan: Map.put(test.plan, :identities, %{@integration => evidence})}
  end

  defp checkpoint(test, outcome, key_sid, integration_token) do
    fingerprint = Credentials.fingerprint(test.credentials)
    context = %{parent_sid: @parent, workspace_token: @workspace, fingerprint: fingerprint}

    record = %{
      sid: @child,
      run_id: String.duplicate("1", 32),
      key_sid: key_sid,
      integration_token: integration_token,
      outcome: outcome
    }

    assert {:ok, _} = Journal.with_lock(context, test.options, &Journal.checkpoint(&1, record))
  end

  defp checkpoints(root) do
    [path] = Path.wildcard(Path.join(root, "*/journal.jsonl"))
    path |> File.read!() |> String.split("\n", trim: true) |> Enum.map(&Jason.decode!/1)
  end
end
