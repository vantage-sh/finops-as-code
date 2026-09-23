# Connect Twilio subaccounts to Vantage

This Livebook connects selected, existing Twilio subaccounts to Vantage. Customers review the accounts and destination before the notebook creates a key or connection. This checkout is a development version; the customer package has not been published or validated through a complete live onboarding run.

## Customer release

The intended customer experience is to install [Livebook Desktop](https://livebook.dev/#install), open a reviewed notebook, and follow its controls. Customers should not need to clone this repository, install Elixir separately, or edit code.

The release notebook will load a pinned Vantage library and start `TwilioOnboarding.Notebook.start/0`. The current Mix app name, `:twilio_onboarding`, is provisional. Do not install a same-named Hex package assuming that it belongs to Vantage. Publishing under a verified Vantage-owned package name, pinning the version and dependency lock, and testing a clean Desktop installation are release requirements.

The guided flow is:

1. Provide credentials through the local Livebook session.
2. Validate the Twilio parent account and Vantage access.
3. Confirm the account identity of any existing Vantage connection that needs review.
4. Select a workspace and active subaccounts, then review their proposed names and actions.
5. Confirm the connection count and create the selected connections.
6. Review individual results and follow their import progress in Vantage.

Use this notebook on your own machine. A notebook can execute code with access to its session credentials, so use the reviewed Vantage release and its pinned dependencies. Do not paste credentials into code cells.

## Run the development notebook

Until the customer package is published, you need this repository's local checkout. Install [Livebook Desktop](https://livebook.dev/#install), then open [twilio_subaccounts.dev.livemd](twilio_subaccounts.dev.livemd) from this directory. Keep the notebook alongside `mix.exs` and `mix.lock`; it loads the library from that folder. Desktop includes the runtime, so running the notebook does not require a separate Elixir installation.

1. Evaluate **Notebook dependencies and setup** at the top to load the local library.
2. Add the three session secrets described below.
3. Evaluate the `TwilioOnboarding.Notebook.start()` cell to show the guided interface.
4. Click **Validate credentials** to load accounts and workspaces. Validation only reads data. If an existing connection needs identification, follow its account-confirmation step before selecting children. Creating keys and connections requires reviewing the accounts and destination, then confirming **Connect**.

### Add session secrets in Livebook

This is the default setup for Desktop. It does not require 1Password or a terminal.

1. Open **Secrets** using the lock icon in the notebook's left sidebar.
2. Click **New secret**. Enter one of the names below and its credential value. Enter the name **without `LB_`**; Livebook displays that prefix separately.
3. Select **only this session**, then click **Add**. Repeat for all three secrets. Newly added session secrets are available to the notebook immediately.

| Session secret name | Value |
| --- | --- |
| `TWILIO_ACCOUNT_SID` | The parent Account SID from [Twilio Account Info](https://console.twilio.com/). It starts with `AC` followed by 32 hexadecimal characters. |
| `TWILIO_AUTH_TOKEN` | The parent's US1 Auth Token. [Find the token](https://help.twilio.com/articles/223136027-Auth-Tokens-and-how-to-change-them) and [check its region](https://www.twilio.com/docs/global-infrastructure/manage-regional-api-credentials). |
| `VANTAGE_API_TOKEN` | A token with Read and Write scopes and permission to manage integrations. See [Vantage authentication](https://docs.vantage.sh/api/authentication/) and [integration roles](https://docs.vantage.sh/connecting_twilio/). |

Livebook exposes these to the runtime as `LB_TWILIO_ACCOUNT_SID`, `LB_TWILIO_AUTH_TOKEN`, and `LB_VANTAGE_API_TOKEN`. If you use an existing saved workspace secret, enable its switch in the Secrets panel to grant the notebook access. For a temporary run, prefer **only this session** over saving credentials to a workspace. See [Livebook's secret management overview](https://livebook.dev/blog/hubs-and-secret-management-launch-week-1-day-3/).

If validation reports missing credentials, check that all three names exist and are available to the notebook. If it reports invalid credentials, check the Account SID format and copy complete tokens without spaces or line breaks. Click **Validate credentials** again after correcting them. These setup errors occur before any API requests.

After use, remove the secrets in Livebook and close the notebook session. **Clear view** only resets the interface; it does not remove secrets. Keep credential values out of notebook cells, saved outputs, screenshots, shell history, and support messages.

### Optional: inject secrets with 1Password

If you already use the [1Password CLI](https://developer.1password.com/docs/cli/secrets-scripts/#use-op-run-to-pass-secrets-using-secret-references), you can inject secrets when starting Livebook Desktop or the Livebook CLI. Create an ignored `op.env` file in this directory with the following **references only**:

```dotenv
LB_TWILIO_ACCOUNT_SID="op://YOUR VAULT/Twilio/parent account sid"
LB_TWILIO_AUTH_TOKEN="op://YOUR VAULT/Twilio/parent auth token"
LB_VANTAGE_API_TOKEN="op://YOUR VAULT/Vantage/api token"
```

Replace the `op://` paths with references to your existing 1Password fields. Keep the quotes so names with spaces work. Do not replace references with credential values.

For **Livebook Desktop on macOS**, fully quit Livebook first; closing its window is not enough. An already running app receives the request to open the notebook but does not receive the new environment variables. Then run this command from this directory:

```sh
op run --env-file=op.env -- /Applications/Livebook.app/Contents/MacOS/livebook \
  "$PWD/twilio_subaccounts.dev.livemd"
```

This uses the installed Desktop app and its bundled runtime. It does not require the Livebook CLI. If Livebook is installed elsewhere, adjust the executable path.

If you use the [Livebook CLI](https://github.com/livebook-dev/livebook#installation), start a new server from this directory instead:

```sh
op run --env-file=op.env -- livebook server twilio_subaccounts.dev.livemd
```

Livebook imports these startup variables as session secrets. Evaluate **Notebook dependencies and setup**, then the `TwilioOnboarding.Notebook.start()` cell. Neither step calls Twilio or Vantage; **Validate credentials** makes the first read-only API requests. Creating connections still requires reviewing the selection and confirming **Connect**.

Another secret manager can inject the same variables into a new process. Fully quit Desktop or stop the CLI process when finished. To add credentials to an already running Desktop app, use its Secrets panel.

## Credentials and permissions

| Credential | Purpose | Documentation |
| --- | --- | --- |
| Twilio parent Account SID and Auth Token | Discover subaccounts and create an account-specific key for each selected child. The parent Auth Token is sent only to Twilio. | [Find and manage Auth Tokens](https://help.twilio.com/articles/223136027-Auth-Tokens-and-how-to-change-them), [regional API credentials](https://www.twilio.com/docs/global-infrastructure/manage-regional-api-credentials) |
| Vantage API token | Read integrations and workspaces, create integrations, and assign new connections to the selected workspace. Read and Write scopes alone do not replace integration-management permissions. | [API authentication and permissions](https://docs.vantage.sh/api/authentication/) |
| Generated Twilio child key | Let Vantage ingest the selected child's usage. Only that child's key and secret are sent to Vantage. | [Twilio key resource and permissions](https://www.twilio.com/docs/iam/api-keys/key-resource-v1), [Vantage Twilio permissions](https://docs.vantage.sh/connecting_twilio/) |

**Twilio Standard keys are not read-only.** They have broad permissions within their account, except access to Accounts and Keys resources. Separate child keys limit which account each key can access; they do not restrict the key to billing reads. Restricted-key support needs separate verification against Vantage's usage requests.

The current adapter uses Twilio's default API hosts. Regional credentials are not interchangeable, so verify the credential region before testing.

## Cost coverage and existing connections

This version connects active children of the validated parent. It does not create Twilio accounts or connect the parent itself. Child-only connections exclude usage incurred directly by the parent. A parent connection includes subaccount costs, so connecting both scopes produces overlapping costs. See [Vantage's Twilio coverage](https://docs.vantage.sh/connecting_twilio/) and [Twilio usage records](https://www.twilio.com/docs/usage/api/usage-record).

Before selecting children, identify any existing Vantage Twilio connections that the notebook cannot verify. Each unresolved connection has a link to its exact settings page:

1. Open the connection's link in Vantage.
2. Copy **Account Details → Account SID** into the matching notebook row.
3. Explicitly confirm that account. The notebook reads the exact account from Twilio and verifies its actual owner. Only new child connections must belong to the validated parent.

Account names and description markers are hints, not proof of identity. Unknown accounts, accounts that cannot be checked with the supplied credentials, and duplicate account identities remain blockers. A verified parent connection also blocks creation because its costs overlap with child connections. Verified existing children are skipped; the notebook does not change their workspace access. Confirming an identity does not edit the existing integration or create a key.

Manual confirmations last only for the current notebook session. **Validate credentials** or **Refresh accounts** starts a fresh inventory and requires those confirmations again. For connections created successfully by this notebook, local recovery records can restore the exact integration-token and Account SID mapping.

If you have changed a notebook-created connection's credentials in Vantage, use **Review existing connections** and confirm its current Account SID again. The saved creation record describes the original connection; the public API cannot reveal every later credential change.

Use one operator for onboarding and avoid creating or editing Twilio integrations elsewhere during the run. The notebook refreshes the inventory before creating connections, but another client can still create one between the check and the write. Preventing that race completely requires duplicate protection in the Vantage API.

New connections are assigned to the selected workspace. “Connected” means Vantage has accepted the integration and begun onboarding, not that all costs are available. Check the integration's import status and workspace access in Vantage using the [Twilio integration guide](https://docs.vantage.sh/connecting_twilio/).

## Interrupted runs

This version supports local macOS and Linux runtimes with filesystems that enforce Unix permissions and directory synchronization. Other platforms stop before any remote writes.

The library stores recovery records beneath `$XDG_STATE_HOME/vantage-twilio-onboarding`, or `~/.local/state/vantage-twilio-onboarding` when `XDG_STATE_HOME` is unset. Records contain account, key, and integration identifiers, run outcomes, destination information, and a credential fingerprint. They do not contain Auth Tokens, API tokens, or child key secrets. The directory and files are restricted to the local user.

Keep these records when restarting an interrupted run. A timeout can mean that a write succeeded even though its response was lost. Reconcile the recorded state before retrying; do not delete the journal to force another connection attempt. Some uncertain outcomes require manual review because Twilio does not return an existing key's secret again.

Successful connections are preserved. There is no blanket undo: removing an integration affects imported costs, and deleting its Twilio key can break ongoing ingestion. Cleanup must identify the exact resource and establish whether Vantage uses it.

## Develop locally

Changing the library and running its checks requires a local checkout and Elixir matching `mix.exs`. For running the notebook in Desktop, follow the setup above.

From this directory:

```sh
mix deps.get
mix check
```

`mix check` checks formatting, compiles with warnings treated as errors, runs ExUnit, and runs strict Credo checks. For a focused planning change:

```sh
mix test test/twilio_onboarding/core/plan_test.exs
```

After changing library code, use **Reconnect and setup**, then evaluate `TwilioOnboarding.Notebook.start()` again. A browser refresh does not reload the library. To load notebook text changed on disk, close the notebook session and reopen the file; add its session secrets again when needed.

## Library layout

| Path or entry point | Responsibility |
| --- | --- |
| `TwilioOnboarding.Notebook.start/0` | Start the guided Livebook interface. |
| `lib/twilio_onboarding/core/` | Pure inventory projection, validation, planning, payload construction, and recovery decisions. |
| `lib/twilio_onboarding/api/` | Authenticated HTTP requests, pagination, and remote response validation. |
| `lib/twilio_onboarding/execution/` | Ordered writes and reconciliation around each account's checkpoints. |
| `lib/twilio_onboarding/journal.ex` | Private local recovery storage and run locking. |
| `test/` | Pure behavior tests and controlled adapter tests without customer API calls. |

The notebook contains the introduction and library entry point. Implementation stays in small, testable modules rather than being copied into notebook cells.

## Before customer release

- Publish a reviewed library under a verified Vantage-owned package name and produce the version-pinned notebook with its dependency lock.
- Verify Desktop startup, session-secret storage, exports, errors, and logs with canary credentials. Confirm that no secret appears in saved artifacts.
- Complete a controlled live run through usable Vantage costs, workspace access, interrupted writes, and recovery.
- Verify guided identity confirmation against manually created connections, fresh inventories, and successful recovery records. Keep the one-operator requirement visible while the Vantage API lacks account SID duplicate protection.
- Document supported Twilio regions and verify whether restricted keys can replace Standard keys for all required usage requests.

## License and interface assets

The original code and notebook in `livebook/twilio-subaccounts/` are licensed under [MIT](LICENSE). This license applies to this directory only. It does not license the rest of `finops-as-code`.

The interface follows Vantage Core's light design tokens, Inter typography, purple controls, and compact account tables. Its Vantage wordmark and Twilio icon are the same SVG assets used by Core. Styling is scoped to the onboarding panel; Livebook's editor keeps its own theme.

The package bundles its font and logos locally. Rendering the interface does not contact Google Fonts or an image CDN. Third-party assets retain the terms and ownership below.

### Inter

Copyright 2016 The Inter Project Authors.

`lib/twilio_onboarding/notebook/assets/fonts/InterVariable.woff2` is an unchanged copy of Inter v4.1, distributed under the SIL Open Font License 1.1. The full copyright notice and license are bundled in [OFL.txt](lib/twilio_onboarding/notebook/assets/fonts/OFL.txt).

- [Upstream font](https://github.com/rsms/inter/blob/e3a3d4c57d5ecc01453a575621882a384c1995a3/docs/font-files/InterVariable.woff2)
- [Upstream license](https://github.com/rsms/inter/blob/e3a3d4c57d5ecc01453a575621882a384c1995a3/LICENSE.txt)
- SHA-256: `693b77d4f32ee9b8bfc995589b5fad5e99adf2832738661f5402f9978429a8e3`

### Vantage and Twilio branding

The Vantage wordmark and Twilio icon identify the services connected by this workflow. The MIT license does not grant rights to use Vantage or Twilio trademarks.

Both SVG files are copied unchanged from Vantage Core:

| Bundled asset | Core source |
| --- | --- |
| `lib/twilio_onboarding/notebook/assets/vantage.svg` | `app/assets/images/logo.svg` |
| `lib/twilio_onboarding/notebook/assets/twilio.svg` | `app/assets/images/icon-twilio.svg` |

The light palette and component dimensions follow Core's `app/javascript/styles/tokens.css` and its Button, Input, Checkbox, and Badge components. Core's Twilio settings page provides the provider tile and account-table layout references.
