defmodule TwilioOnboarding.Journal.StorageTest do
  use ExUnit.Case, async: true

  alias TwilioOnboarding.Core.Storage, as: Policy
  alias TwilioOnboarding.Journal.Storage

  setup do
    temp = if File.dir?("/private/tmp"), do: "/private/tmp", else: "/tmp"
    root = Path.join(temp, "twilio-storage-test-" <> Base.encode16(:crypto.strong_rand_bytes(8)))
    on_exit(fn -> File.rm_rf!(root) end)
    %{root: root, directory: Path.join(root, "recovery")}
  end

  test "unsupported runtimes fail before creating any directory", test do
    assert {:error, :unsupported_platform} = Storage.prepare(test.root, test.directory, {:win32, :nt})
    assert {:error, :unsupported_platform} = Storage.prepare(test.root, test.directory, {:unix, :freebsd})
    refute File.exists?(test.root)
  end

  test "the current supported platform creates private synced directories", test do
    assert Policy.supported_platform?(:os.type())
    assert :ok = Storage.prepare(test.root, test.directory)
    assert Policy.private_mode?(File.stat!(test.root).mode, 0o700)
    assert Policy.private_mode?(File.stat!(test.directory).mode, 0o700)
    assert :ok = Storage.sync_parent(test.directory)
  end

  test "privacy requires owner-only access and rejects special permission bits" do
    refute Policy.private_mode?(0o100644, 0o600)
    refute Policy.private_mode?(0o40777, 0o700)
    refute Policy.private_mode?(0o104600, 0o600)
  end

  test "private permissions are read back after chmod", test do
    assert :ok = Storage.prepare(test.root, test.directory)
    path = Path.join(test.directory, "journal.jsonl")
    File.write!(path, "")
    File.chmod!(path, 0o644)
    assert :ok = Storage.permissions(path, 0o600)
    assert Policy.private_mode?(File.stat!(path).mode, 0o600)
  end

  test "hard links are rejected without modifying the source", test do
    assert :ok = Storage.prepare(test.root, test.directory)
    path = Path.join(test.directory, "source")
    linked = Path.join(test.directory, "linked")
    File.write!(path, "unchanged")
    File.chmod!(path, 0o644)
    File.ln!(path, linked)
    assert {:error, :journal_unavailable} = Storage.permissions(linked, 0o600)
    assert File.read!(path) == "unchanged"
    assert Bitwise.band(File.stat!(path).mode, 0o777) == 0o644
  end

  test "locking is exclusive and release permits the next run", test do
    assert :ok = Storage.prepare(test.root, test.directory)
    path = Path.join(test.root, "run.lock")
    assert :ok = Storage.acquire_lock(path)
    assert {:error, :run_locked} = Storage.acquire_lock(path)
    assert :ok = Storage.release_lock(path)
    assert :ok = Storage.acquire_lock(path)
    assert :ok = Storage.release_lock(path)
  end

  test "a parent that cannot be opened for synchronization fails closed", test do
    assert {:error, :journal_unavailable} = Storage.sync_parent(Path.join(test.directory, "missing"))
  end
end
