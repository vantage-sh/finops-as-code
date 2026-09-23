defmodule TwilioOnboarding.Journal do
  @moduledoc "Stores secret-free, synced recovery checkpoints under a private local directory."

  alias TwilioOnboarding.Core.Identifiers
  alias TwilioOnboarding.Journal.Storage

  @record_fields [:sid, :run_id, :key_sid, :integration_token, :outcome]
  @outcomes ~w(key_pending key_created key_unknown integration_pending integration_unknown integration_created complete cleanup_pending cleanup_failed rejected)
  @maximum_bytes 8_000_000

  @doc "Reads saved outcomes for the same parent and Vantage credential before choosing a workspace."
  @spec records(map(), keyword()) :: {:ok, map()} | {:error, atom()}
  def records(context, options \\ []) do
    context = Map.take(context, [:parent_sid, :fingerprint])
    with_lock(context, options, &{:ok, &1.records})
  end

  @doc "Runs a callback with exclusive access to a context's recovery journal."
  @spec with_lock(map(), keyword(), (map() -> term())) :: term()
  def with_lock(context, options, callback) do
    root = Keyword.get_lazy(options, :state_root, &default_root/0)
    directory = Path.join(root, context_id(context))
    lock = Path.join(root, context_id(context) <> ".lock")

    with :ok <- Storage.prepare(root, directory),
         :ok <- Storage.acquire_lock(lock) do
      try do
        with {:ok, journal} <- load(Path.join(directory, "journal.jsonl"), context) do
          callback.(journal)
        end
      after
        Storage.release_lock(lock)
      end
    end
  end

  @doc "Persists an allowlisted account checkpoint and syncs it before returning."
  @spec checkpoint(map(), map()) :: {:ok, map()} | {:error, atom()}
  def checkpoint(journal, record) do
    record = Map.take(record, @record_fields)

    with true <- valid_record?(record),
         :ok <- ensure_initialized(journal),
         :ok <- append(journal.path, record) do
      {:ok, %{journal | records: Map.put(journal.records, record.sid, record)}}
    else
      false -> {:error, :journal_invalid}
      error -> error
    end
  end

  @doc "Returns the default customer-local recovery directory."
  @spec default_root() :: String.t()
  def default_root do
    state_home = System.get_env("XDG_STATE_HOME") || Path.join(System.user_home!(), ".local/state")
    Path.join(state_home, "vantage-twilio-onboarding")
  end

  defp context_id(context) do
    :sha256
    |> :crypto.hash(context.parent_sid)
    |> Base.encode16(case: :lower)
  end

  defp load(path, context) do
    header = Map.put(context, :version, 1)

    case File.lstat(path) do
      {:error, :enoent} -> {:ok, %{path: path, header: header, records: %{}}}
      {:ok, %{type: :regular, links: 1, size: size}} when size <= @maximum_bytes -> read(path, header)
      _ -> {:error, :journal_invalid}
    end
  end

  defp ensure_initialized(journal) do
    case File.lstat(journal.path) do
      {:error, :enoent} when map_size(journal.records) == 0 -> initialize(journal.path, journal.header)
      {:ok, %{type: :regular, links: 1}} -> :ok
      _ -> {:error, :journal_unavailable}
    end
  end

  defp initialize(path, header) do
    case File.open(path, [:write, :binary, :exclusive]) do
      {:ok, file} ->
        result = write_synced(file, path, header)
        File.close(file)

        case result do
          :ok -> Storage.sync_parent(path)
          _ -> {:error, :journal_unavailable}
        end

      _ ->
        {:error, :journal_unavailable}
    end
  end

  defp read(path, header) do
    with :ok <- Storage.permissions(path, 0o600),
         {:ok, content} <- File.read(path),
         true <- String.ends_with?(content, "\n"),
         [first | lines] <- String.split(content, "\n", trim: true),
         {:ok, saved_header} <- Jason.decode(first),
         true <- is_map(saved_header),
         :ok <- verify_header(saved_header, header),
         {:ok, records} <- read_records(lines) do
      {:ok, %{path: path, header: header, records: records}}
    else
      {:error, :credentials_changed} = error -> error
      {:error, :destination_changed} = error -> error
      _ -> {:error, :journal_invalid}
    end
  end

  defp verify_header(saved, expected) do
    expected = Map.new(expected, fn {key, value} -> {Atom.to_string(key), value} end)

    verify_context(saved, expected)
  end

  defp verify_context(saved, expected) when not is_map_key(expected, "workspace_token") do
    if Identifiers.workspace_token?(saved["workspace_token"]) do
      verify_context(saved, Map.put(expected, "workspace_token", saved["workspace_token"]))
    else
      {:error, :journal_invalid}
    end
  end

  defp verify_context(saved, expected) do
    cond do
      saved == expected -> :ok
      Map.delete(saved, "fingerprint") == Map.delete(expected, "fingerprint") -> {:error, :credentials_changed}
      Map.delete(saved, "workspace_token") == Map.delete(expected, "workspace_token") -> {:error, :destination_changed}
      true -> {:error, :journal_invalid}
    end
  end

  defp read_records(lines) do
    Enum.reduce_while(lines, {:ok, %{}}, fn line, {:ok, records} ->
      with {:ok, decoded} <- Jason.decode(line),
           true <- is_map(decoded),
           record = Map.new(@record_fields, &{&1, Map.get(decoded, Atom.to_string(&1))}),
           true <- map_size(decoded) == map_size(record),
           true <- valid_record?(record) do
        {:cont, {:ok, Map.put(records, record.sid, record)}}
      else
        _ -> {:halt, {:error, :journal_invalid}}
      end
    end)
  end

  defp valid_record?(record) do
    map_size(record) == length(@record_fields) and
      Identifiers.account_sid?(record.sid) and
      valid_id?(record.run_id, ~r/\A[0-9a-f]{32}\z/) and
      (is_nil(record.key_sid) or Identifiers.key_sid?(record.key_sid)) and
      (is_nil(record.integration_token) or Identifiers.integration_token?(record.integration_token)) and
      record.outcome in @outcomes
  end

  defp valid_id?(value, pattern) when is_binary(value), do: Regex.match?(pattern, value)
  defp valid_id?(_, _), do: false

  defp append(path, value) do
    with {:ok, %{type: :regular, links: 1, size: size}} when size < @maximum_bytes <- File.lstat(path),
         {:ok, file} <- File.open(path, [:append, :binary]) do
      result = write_synced(file, path, value)
      File.close(file)
      result
    else
      _ -> {:error, :journal_unavailable}
    end
  end

  defp write_synced(file, path, value) do
    with :ok <- Storage.permissions(path, 0o600),
         :ok <- IO.binwrite(file, Jason.encode!(value) <> "\n"),
         :ok <- :file.sync(file) do
      :ok
    else
      _ -> {:error, :journal_unavailable}
    end
  end
end
