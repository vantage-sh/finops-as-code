"""Exercise account guards and interrupted-create recovery without AWS resources."""
from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import Mock, patch

import boto3
from botocore.exceptions import ClientError, ReadTimeoutError
from botocore.stub import Stubber

from bedrock_demo.aws.deployment import describe_owned_stack, inspect_unit, start_or_resume_stack
from bedrock_demo.core.deployment import creation_intent, fingerprint, stack_creation_tags

ACCOUNT = "111122223333"
REGION = "us-east-1"
DEPLOYMENT = "test-bedrock"
STACK_NAME = "bedrock-demo-source"
STACK_ID = (f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{STACK_NAME}/"
            "00000000-0000-0000-0000-000000000000")
TEMPLATE = '{"Resources":{"Logs":{"Type":"AWS::S3::Bucket"}}}'
PARAMETERS = [{"ParameterKey": "LogBucketName", "ParameterValue": "example-bedrock-logs"}]
UNIT = {"kind": "source", "account_id": ACCOUNT, "region": REGION, "profile": "example",
        "stack_name": STACK_NAME, "bucket_name": "example-bedrock-logs"}
SAVED_UNIT = {**UNIT, "stack_id": STACK_ID}
INTENT = creation_intent(UNIT, TEMPLATE, PARAMETERS)


def stack_response(status: str = "CREATE_COMPLETE", *, deployment_id: str = DEPLOYMENT,
                   intent_hash: str = INTENT) -> dict:
    """Return a model-valid CloudFormation response with test ownership markers."""
    return {"StackId": STACK_ID, "StackName": STACK_NAME,
            "CreationTime": datetime(2026, 9, 14, tzinfo=timezone.utc), "StackStatus": status,
            "Tags": stack_creation_tags(deployment_id, intent_hash),
            "Outputs": [{"OutputKey": "LogBucket", "OutputValue": UNIT["bucket_name"]}]}


def create_request() -> dict:
    """Return the expected create request, including its retry token and ownership tags."""
    token = f"bedrock-{fingerprint({'deployment_id': DEPLOYMENT, 'intent_hash': INTENT})}"
    return {"StackName": STACK_NAME, "TemplateBody": TEMPLATE, "Parameters": PARAMETERS,
            "Capabilities": ["CAPABILITY_NAMED_IAM"],
            "Tags": stack_creation_tags(DEPLOYMENT, INTENT), "ClientRequestToken": token}


class DeploymentAWSTest(unittest.TestCase):
    """Stub every AWS response so an unplanned API call fails the test."""

    def setUp(self) -> None:
        """Create clients with inert credentials and activate strict response queues."""
        real = boto3.session.Session(aws_access_key_id="testing", aws_secret_access_key="testing",
                                     region_name=REGION)
        self.clients = {name: real.client(name) for name in ("sts", "cloudformation", "bedrock")}
        self.stubs = {name: Stubber(client) for name, client in self.clients.items()}
        for stub in self.stubs.values():
            stub.activate()
            self.addCleanup(stub.deactivate)
        self.session = Mock(spec=boto3.session.Session)
        self.session.client.side_effect = lambda service, **kwargs: self.clients[service]

    def tearDown(self) -> None:
        """Require every expected read or create call to have occurred."""
        for stub in self.stubs.values():
            stub.assert_no_pending_responses()

    def add_identity(self, account: str = ACCOUNT) -> None:
        """Queue a caller identity for one guarded operation."""
        self.stubs["sts"].add_response("get_caller_identity", {
            "Account": account, "Arn": f"arn:aws:iam::{account}:user/example",
            "UserId": "example"}, {})

    def add_missing_stack(self, name: str = STACK_NAME) -> None:
        """Queue only the missing-stack validation error that permits a fresh create."""
        self.stubs["cloudformation"].add_client_error(
            "describe_stacks", service_error_code="ValidationError",
            service_message=f"Stack with id {name} does not exist",
            expected_params={"StackName": name})

    def add_stack(self, stack: dict, name: str = STACK_NAME) -> None:
        """Queue one exact-name or exact-ID stack lookup."""
        self.stubs["cloudformation"].add_response("describe_stacks", {"Stacks": [stack]},
                                                  {"StackName": name})

    def add_unconfigured_logging(self) -> None:
        """Queue a source account whose logging remains available for a new stack."""
        self.stubs["bedrock"].add_response("get_model_invocation_logging_configuration", {}, {})

    def add_create_error(self, code: str, message: str) -> None:
        """Queue one create_stack failure for the exact planned request."""
        self.stubs["cloudformation"].add_client_error(
            "create_stack", service_error_code=code, service_message=message,
            expected_params=create_request())

    def start(self, unit: dict = UNIT) -> dict:
        """Run the guarded create-or-resume for one unit against the stubbed session."""
        return start_or_resume_stack(unit, DEPLOYMENT, TEMPLATE, PARAMETERS, session=self.session)

    def test_plan_checks_identity_before_resource_access(self) -> None:
        """Reject the wrong AWS profile before inspecting or creating target resources."""
        self.add_identity("999900001111")
        with self.assertRaisesRegex(ValueError, f"expected {ACCOUNT}"):
            inspect_unit(UNIT, DEPLOYMENT, TEMPLATE, session=self.session)

    def test_apply_checks_identity_before_resource_access(self) -> None:
        """Repeat the account guard when applying a previously valid plan."""
        self.add_identity("999900001111")
        with self.assertRaisesRegex(ValueError, f"expected {ACCOUNT}"):
            self.start()

    def test_plan_rejects_an_existing_stack_even_with_matching_tags(self) -> None:
        """Require the saved manifest instead of silently adopting an existing deployment."""
        self.add_identity()
        self.add_stack(stack_response())
        with self.assertRaisesRegex(ValueError, "already exists"):
            inspect_unit(UNIT, DEPLOYMENT, session=self.session)

    def test_plan_rejects_existing_source_logging(self) -> None:
        """Preserve logging owned by another setup before deploying any resources."""
        self.add_identity()
        self.add_missing_stack()
        self.stubs["bedrock"].add_response("get_model_invocation_logging_configuration", {
            "loggingConfig": {"s3Config": {"bucketName": "customer-existing-logs"}}}, {})
        with self.assertRaisesRegex(ValueError, "logging already exists"):
            inspect_unit(UNIT, DEPLOYMENT, session=self.session)

    def test_plan_validates_the_actual_template_without_mutation(self) -> None:
        """Save identity and validation evidence after read-only preflight succeeds."""
        self.add_identity()
        self.add_missing_stack()
        self.add_unconfigured_logging()
        self.stubs["cloudformation"].add_response("validate_template", {},
                                                  {"TemplateBody": TEMPLATE})
        result = inspect_unit(UNIT, DEPLOYMENT, TEMPLATE, session=self.session)
        self.assertEqual(ACCOUNT, result["account_id"])
        self.assertTrue(result["template_validated"])
        self.assertFalse(result["stack_exists"])

    def test_create_returns_stack_identity_before_polling(self) -> None:
        """Let the caller persist a new stack ID immediately after the create response."""
        self.add_identity()
        self.add_missing_stack()
        self.add_unconfigured_logging()
        self.stubs["cloudformation"].add_response("create_stack", {"StackId": STACK_ID},
                                                  create_request())
        result = self.start()
        self.assertEqual(STACK_ID, result["stack_id"])
        self.assertEqual("CREATE_IN_PROGRESS", result["status"])
        self.assertEqual(INTENT, result["intent_hash"])
        self.assertEqual(create_request()["ClientRequestToken"], result["request_token"])

    def test_central_plan_does_not_require_bedrock_logging(self) -> None:
        """Allow a log-archive account without reading or enabling its Bedrock logging."""
        self.add_identity()
        self.add_missing_stack()
        result = inspect_unit({**UNIT, "kind": "central"}, DEPLOYMENT, session=self.session)
        self.assertIsNone(result["logging_config"])

    def test_uncertain_create_recovers_by_matching_tags(self) -> None:
        """Recover after a network timeout without creating again or rechecking new logging."""
        self.add_identity()
        self.add_missing_stack()
        self.add_unconfigured_logging()
        timeout = ReadTimeoutError(endpoint_url="https://example.invalid")
        with patch.object(self.clients["cloudformation"], "create_stack", side_effect=timeout):
            with self.assertRaises(ReadTimeoutError):
                self.start()
        self.add_identity()
        self.add_stack(stack_response("CREATE_IN_PROGRESS"))
        result = self.start()
        self.assertEqual(STACK_ID, result["stack_id"])
        self.assertEqual("CREATE_IN_PROGRESS", result["status"])

    def test_resume_rejects_another_deployments_stack(self) -> None:
        """Keep a colliding stack name outside this deployment untouched."""
        self.add_identity()
        self.add_stack(stack_response(deployment_id="someone-else"))
        with self.assertRaisesRegex(ValueError, "not owned"):
            self.start()

    def test_create_name_race_still_checks_ownership(self) -> None:
        """Reject a foreign stack created between absence inspection and our create request."""
        self.add_identity()
        self.add_missing_stack()
        self.add_unconfigured_logging()
        self.add_create_error("AlreadyExistsException", "Stack exists")
        self.add_stack(stack_response(deployment_id="someone-else"))
        with self.assertRaisesRegex(ValueError, "not owned"):
            self.start()

    def test_saved_stack_id_does_not_override_changed_intent(self) -> None:
        """Require ownership markers even when the manifest already knows a stack ID."""
        self.add_identity()
        self.add_stack(stack_response(intent_hash="different-template"), STACK_ID)
        with self.assertRaisesRegex(ValueError, "template and parameters"):
            self.start(SAVED_UNIT)

    def test_missing_recorded_stack_is_not_recreated(self) -> None:
        """Leave retained resources for explicit inspection if a saved stack disappears."""
        self.add_identity()
        self.add_missing_stack(STACK_ID)
        with self.assertRaisesRegex(ValueError, "no longer exists"):
            self.start(SAVED_UNIT)

    def test_other_validation_errors_do_not_look_like_stack_absence(self) -> None:
        """Preserve access and validation errors rather than attempting creation."""
        self.add_identity()
        self.stubs["cloudformation"].add_client_error(
            "describe_stacks", service_error_code="ValidationError",
            service_message="Invalid request", expected_params={"StackName": STACK_NAME})
        with self.assertRaises(ClientError):
            self.start()

    def test_create_failure_is_not_masked(self) -> None:
        """Return the actual AWS error when a stack cannot be created."""
        self.add_identity()
        self.add_missing_stack()
        self.add_unconfigured_logging()
        self.add_create_error("AccessDenied", "Create is denied")
        with self.assertRaisesRegex(ClientError, "Create is denied"):
            self.start()

    def test_failed_stack_status_and_reason_survive_resume(self) -> None:
        """Return failed-stack evidence for persistence without deleting or recreating anything."""
        self.add_identity()
        failed = {**stack_response("ROLLBACK_COMPLETE"),
                  "StackStatusReason": "Missing delivery permission"}
        self.add_stack(failed, STACK_ID)
        result = describe_owned_stack({**SAVED_UNIT, "intent_hash": INTENT}, DEPLOYMENT,
                                      session=self.session)
        self.assertEqual("ROLLBACK_COMPLETE", result["status"])
        self.assertEqual("Missing delivery permission", result["reason"])

    def test_polling_rechecks_ownership_and_returns_outputs(self) -> None:
        """Expose final outputs only after checking the same identity and intent markers."""
        self.add_identity()
        self.add_stack(stack_response(), STACK_ID)
        result = describe_owned_stack({**SAVED_UNIT, "intent_hash": INTENT}, DEPLOYMENT,
                                      session=self.session)
        self.assertEqual({"LogBucket": UNIT["bucket_name"]}, result["outputs"])
        self.assertEqual("CREATE_COMPLETE", result["status"])


if __name__ == "__main__":
    unittest.main()
