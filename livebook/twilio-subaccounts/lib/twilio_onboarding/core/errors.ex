defmodule TwilioOnboarding.Core.Errors do
  @moduledoc "Maps failures to fixed customer messages without rendering remote or secret values."

  @messages %{
    missing_credentials:
      "The notebook cannot access all three credentials. Add TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and VANTAGE_API_TOKEN in Livebook's Secrets panel, grant this notebook access, then validate again.",
    invalid_credentials:
      "Check the Twilio Account SID: it must start with AC followed by 32 hexadecimal characters. Copy both complete tokens without spaces or line breaks, then validate again.",
    invalid_parent:
      "The Twilio credentials must belong to an active parent account. Check the parent Account SID and its matching Auth Token, then validate again.",
    no_workspaces:
      "No Vantage workspaces are available to this token. Check the token's workspace access and validate again.",
    unavailable: "An API could not be reached. Check your connection and review any pending operation before retrying.",
    uncertain:
      "The request may have succeeded without a usable response. Reconcile its outcome before creating another connection.",
    invalid_plan: "The reviewed plan is invalid. Refresh the inventory and review a new plan.",
    invalid_response: "The service returned an unexpected response. Refresh the inventory before continuing.",
    invalid_inventory: "The account inventory is inconsistent. Refresh it before continuing.",
    invalid_destination: "Check the parent account SID and selected Vantage workspace.",
    unidentified_integration:
      "An existing Twilio connection has an unknown account identity. Review it in Vantage before connecting more accounts.",
    parent_already_connected:
      "The parent account is already connected. Its costs overlap with subaccounts; review that connection before continuing.",
    duplicate_integrations:
      "Multiple Vantage connections refer to the same Twilio account. Resolve them before continuing.",
    no_accounts_selected: "Select at least one active subaccount.",
    duplicate_selection: "The selection contains the same account more than once. Refresh the selection.",
    invalid_selection: "Select only active subaccounts belonging to the validated parent account.",
    unauthorized: "The credentials could not authorize this request. Check the credentials and required permissions.",
    forbidden: "The credentials do not have permission for this action. Review the required permissions.",
    rate_limited: "The service is limiting requests. Wait, then refresh or reconcile before retrying.",
    timeout: "The request timed out. Its outcome may be unknown; reconcile before retrying.",
    network_error: "The service could not be reached. Reconcile any pending write before retrying.",
    outcome_unknown: "The write outcome is unknown. Reconcile it before creating another connection.",
    journal_error: "The local recovery record could not be saved. No further writes will run.",
    journal_unavailable:
      "The local recovery record could not be accessed. Check its location and permissions before continuing.",
    unsupported_platform:
      "Local recovery storage currently supports macOS and Linux. Use a supported local runtime before connecting accounts.",
    journal_invalid:
      "The recovery record is incomplete or changed. Preserve it and review the recorded resources before continuing.",
    run_locked:
      "Another run holds the recovery lock. If a process crashed, confirm it has stopped and review its recorded resources before removing the stale lock.",
    credentials_changed:
      "The Vantage credential differs from the saved run. Restore the original credential or review its destination before continuing.",
    destination_changed:
      "The saved run belongs to a different workspace. Restore its destination or review its existing connections before continuing.",
    integration_found_needs_review:
      "A matching integration exists, but this run cannot prove it created it. Review the connection before changing it or its key.",
    cleanup_failed:
      "The known unused key could not be removed. Review its recorded key SID in Twilio before trying cleanup again.",
    cleanup_pending:
      "Key cleanup was interrupted. Check that the recorded key is unused and reconcile its status before continuing.",
    integration_missing:
      "The recorded Vantage integration is missing. Review the integration and its Twilio key before creating a replacement.",
    plan_changed: "The account inventory changed. Refresh and review a new plan before connecting."
  }

  @validation_messages @messages
                       |> Map.take([
                         :missing_credentials,
                         :invalid_credentials,
                         :invalid_parent,
                         :no_workspaces,
                         :invalid_response,
                         :unauthorized,
                         :forbidden
                       ])
                       |> Map.put(
                         :rate_limited,
                         "An API is limiting validation requests. Wait briefly, then validate again. No changes were made."
                       )
                       |> Map.put(
                         :unavailable,
                         "An API could not be reached during validation. Check your connection and try validating again. No changes were made."
                       )

  @doc "Returns a fixed message; arbitrary errors and remote response bodies are never interpolated."
  @spec message(term()) :: String.t()
  def message(reason),
    do: Map.get(@messages, reason, "The operation could not be completed. Review the recovery status before retrying.")

  @doc "Returns read-only validation guidance without implying that a write needs recovery."
  @spec validation_message(term()) :: String.t()
  def validation_message(reason) do
    Map.get(
      @validation_messages,
      reason,
      "Validation could not be completed. Check your session secrets and connection, then validate again. No changes were made."
    )
  end

  @doc "Explains a failed read-only identification while preserving the current reconciliation."
  @spec identification_message(term()) :: String.t()
  def identification_message(reason) when reason in [:unauthorized, :forbidden, :rejected] do
    "Twilio could not verify this account with the current credentials. Copy the Account SID from this Vantage connection's Account Details and try again. An inaccessible account cannot be treated as unrelated."
  end

  def identification_message(_reason) do
    "The Account SID could not be verified. Check this connection's Account Details in Vantage and try again. Your other confirmations are preserved; no changes were made."
  end
end
