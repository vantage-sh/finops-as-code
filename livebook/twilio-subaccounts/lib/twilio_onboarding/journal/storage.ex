defmodule TwilioOnboarding.Journal.Storage do
  @moduledoc "Enforces private Unix storage and syncs directory entries before remote writes."

  alias TwilioOnboarding.Core.Storage, as: Policy

  @doc "Prepares private recovery directories only on supported platforms."
  @spec prepare(String.t(), String.t(), {atom(), atom()}) :: :ok | {:error, atom()}
  def prepare(root, directory, platform \\ :os.type()) do
    with true <- Policy.supported_platform?(platform),
         :ok <- private_directory(root) do
      private_directory(directory)
    else
      false -> {:error, :unsupported_platform}
      error -> error
    end
  end

  @doc "Acquires a parent-account lock and durably records the new directory entry."
  @spec acquire_lock(String.t()) :: :ok | {:error, atom()}
  def acquire_lock(path) do
    case File.mkdir(path) do
      :ok ->
        with :ok <- permissions(path, 0o700) do
          sync_parent(path)
        end

      {:error, :eexist} ->
        {:error, :run_locked}

      _ ->
        {:error, :journal_unavailable}
    end
  end

  @doc "Removes a completed process lock and syncs its parent directory."
  @spec release_lock(String.t()) :: :ok | {:error, atom()}
  def release_lock(path) do
    with :ok <- File.rmdir(path) do
      sync_parent(path)
    end
  end

  @doc "Sets and verifies permissions without following a symlink or a hard-linked file."
  @spec permissions(String.t(), 0o600 | 0o700) :: :ok | {:error, :journal_unavailable}
  def permissions(path, expected) do
    with {:ok, before} <- File.lstat(path),
         true <- valid_kind?(before, expected),
         :ok <- File.chmod(path, expected),
         {:ok, after_stat} <- File.lstat(path),
         true <- valid_kind?(after_stat, expected),
         true <- Policy.private_mode?(after_stat.mode, expected) do
      :ok
    else
      _ -> {:error, :journal_unavailable}
    end
  end

  @doc "Flushes the containing directory so newly created checkpoint paths survive a crash."
  @spec sync_parent(String.t()) :: :ok | {:error, :journal_unavailable}
  def sync_parent(path) do
    directory = path |> Path.dirname() |> String.to_charlist()

    case :file.open(directory, [:read, :raw, :directory]) do
      {:ok, file} ->
        result = :file.sync(file)
        :file.close(file)
        normalize(result)

      _ ->
        {:error, :journal_unavailable}
    end
  end

  defp private_directory(path) do
    case ensure_directory(Path.expand(path)) do
      :ok -> permissions(path, 0o700)
      _ -> {:error, :journal_unavailable}
    end
  end

  defp ensure_directory(path) do
    case File.lstat(path) do
      {:ok, %{type: :directory}} -> ensure_parent(path)
      {:error, :enoent} -> create_directory(path)
      _ -> {:error, :journal_unavailable}
    end
  end

  defp ensure_parent("/"), do: :ok
  defp ensure_parent(path), do: ensure_directory(Path.dirname(path))

  defp create_directory(path) do
    with :ok <- ensure_parent(path),
         :ok <- File.mkdir(path),
         :ok <- permissions(path, 0o700) do
      sync_parent(path)
    end
  end

  defp valid_kind?(%{type: :directory}, 0o700), do: true
  defp valid_kind?(%{type: :regular, links: 1}, 0o600), do: true
  defp valid_kind?(_, _), do: false
  defp normalize(:ok), do: :ok
  defp normalize(_error), do: {:error, :journal_unavailable}
end
