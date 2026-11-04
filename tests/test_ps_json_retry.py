"""Regression coverage for PS gateway errors carried inside HTTP 200 JSON."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, call

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import common as transport

URL = "https://web.np.playstation.com/api/graphql/v1//op?operationName=categoryGridRetrieve"
FAILURE = {"errors": [{"message": "", "path": ["categoryGridRetrieve"],
    "extensions": {"type": "NimbusNormalizedError", "statusCode": 500,
                   "error": {"code": 3165954, "reason": "internal_error"}}}],
    "data": {"categoryGridRetrieve": None}}
SUCCESS = {"data": {"categoryGridRetrieve": {"pageInfo": {"totalCount": 1}, "products": [{"id": "example"}]}}}
BREAKER = {"errors": [{"message": "Breaker is open", "path": ["categoryGridRetrieve"],
    "extensions": {"type": "NimbusNormalizedError", "apiName": "getCategory"}}],
    "data": {"categoryGridRetrieve": None}}


class PSJSONRetryTests(unittest.TestCase):
    def run_read(self, responses, url=URL, body=None, headers=None):
        client = transport.Client(delay=0)
        with patch.object(client, "request", side_effect=[json.dumps(r) for r in responses]) as request, \
             patch.object(transport.time, "sleep") as sleep:
            result = client.json(url, body, headers)
        return result, request, sleep

    def test_actual_http_200_upstream_500_recovers_same_category(self):
        result, request, sleep = self.run_read([FAILURE, SUCCESS])
        self.assertEqual(result, SUCCESS)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].args[0], URL)
        self.assertEqual(request.call_args_list[1].args[0], URL)
        self.assertEqual(request.call_args_list[1].args[2]["Cache-Control"], "no-cache")
        sleep.assert_called_once_with(10)

    def test_persistent_failure_is_returned_for_existing_source_validation(self):
        result, request, sleep = self.run_read([FAILURE] * 3)
        self.assertEqual(result, FAILURE)
        self.assertEqual(request.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(10), call(30)])
        self.assertIsNone(result["data"]["categoryGridRetrieve"])

    def test_last_allowed_attempt_can_succeed(self):
        result, request, sleep = self.run_read([FAILURE, FAILURE, SUCCESS])
        self.assertEqual(result, SUCCESS)
        self.assertEqual(request.call_count, 3)

    def test_actual_upstream_500_then_circuit_breaker_can_recover(self):
        result, request, sleep = self.run_read([FAILURE, BREAKER, SUCCESS])
        self.assertEqual(result, SUCCESS)
        self.assertEqual(request.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(10), call(30)])

    def test_open_circuit_is_bounded_and_requires_recognized_identity(self):
        result, request, sleep = self.run_read([BREAKER] * 3)
        self.assertEqual(result, BREAKER)
        self.assertEqual(request.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(10), call(30)])
        for extensions in ({}, {"type": "Other", "apiName": "getCategory"},
                           {"type": "NimbusNormalizedError", "apiName": "other"},
                           {"type": "NimbusNormalizedError", "apiName": "getCategory", "statusCode": 401}):
            failure = {"errors": [{"message": "Breaker is open", "path": ["categoryGridRetrieve"],
                                   "extensions": extensions}]}
            result, request, sleep = self.run_read([failure])
            self.assertEqual(result, failure)
            request.assert_called_once()
            sleep.assert_not_called()

    def test_error_codes_only_retry_recognized_transient_failures(self):
        for status in [408, 429, 500, 502, 503, 504]:
            with self.subTest(status=status):
                failure = {"errors": [{"path": ["categoryGridRetrieve"], "statusCode": status}]}
                result, request, _ = self.run_read([failure, SUCCESS])
                self.assertEqual(result, SUCCESS)
                self.assertEqual(request.call_count, 2)
        for status in [400, 401, 403, 404, "500", None, True]:
            with self.subTest(status=status):
                failure = {"errors": [{"path": ["categoryGridRetrieve"], "extensions": {"statusCode": status}}]}
                result, request, sleep = self.run_read([failure])
                self.assertEqual(result, failure)
                request.assert_called_once()
                sleep.assert_not_called()

    def test_other_hosts_and_posts_are_not_retried(self):
        for url, body in [("https://example.com/api", None),
                          ("https://web.np.playstation.com.example.com/api", None),
                          (URL, {"mutation": "example"})]:
            result, request, sleep = self.run_read([FAILURE], url=url, body=body)
            self.assertEqual(result, FAILURE)
            request.assert_called_once()
            sleep.assert_not_called()

    def test_normal_json_and_unrecognized_errors_are_unchanged(self):
        values = [SUCCESS, [], {"errors": []}, {"errors": "bad format"},
                  {"errors": [None]}, {"errors": [{"path": [], "statusCode": 500}]},
                  {"errors": [{"path": "categoryGridRetrieve", "statusCode": 500}]},
                  {"errors": [{"path": ["otherOperation"], "statusCode": 500}]},
                  {"errors": [{"message": "PersistedQueryNotFound"}]},
                  {"errors": FAILURE["errors"] + [{"path": ["categoryGridRetrieve"], "statusCode": 400}]}]
        for value in values:
            with self.subTest(value=value):
                result, request, sleep = self.run_read([value])
                self.assertEqual(result, value)
                request.assert_called_once()
                sleep.assert_not_called()

    def test_invalid_json_remains_a_source_failure(self):
        client = transport.Client(delay=0)
        with patch.object(client, "request", return_value="<html>maintenance</html>") as request, \
             patch.object(transport.time, "sleep") as sleep:
            with self.assertRaises(transport.SourceError):
                client.json(URL)
        request.assert_called_once()
        sleep.assert_not_called()

    def test_caller_headers_preserved_without_mutation(self):
        headers = {"x-psn-store-locale-override": "en-US", "Cache-Control": "max-age=0"}
        result, request, _ = self.run_read([FAILURE, SUCCESS], headers=headers)
        self.assertEqual(result, SUCCESS)
        self.assertEqual(headers["Cache-Control"], "max-age=0")
        self.assertEqual(request.call_args_list[-1].args[2]["x-psn-store-locale-override"], "en-US")


if __name__ == "__main__":
    unittest.main()
