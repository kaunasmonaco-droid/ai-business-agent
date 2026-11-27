import unittest
from unittest.mock import patch

from sales import build_drafts


class SalesPipelineTests(unittest.TestCase):
    def setUp(self):
        contact = patch("sales.contact_request", return_value={"id": "789"})
        self.contact_request = contact.start()
        self.addCleanup(contact.stop)
        self.record = {
            "status": "ok",
            "source_url": "https://www.example.com/contact",
            "title": "Example Fabrication",
            "description": "Metal profile fabrication",
            "keyword_matches": ["metal", "export"],
            "generic_contact_emails": ["export@example.com"],
        }

    @patch("sales.hubspot_request")
    def test_reuses_company_and_writes_one_unsent_draft(self, request):
        request.return_value = {"results": [{"id": "123"}]}
        draft, = build_drafts([self.record, self.record], token="test")
        self.assertEqual(draft["hubspot_company_id"], "123")
        self.assertEqual(draft["hubspot_status"], "existing")
        self.assertEqual(draft["status"], "draft")
        self.assertIn("metal, export", draft["body"])
        request.assert_called_once()
        self.assertEqual(draft["hubspot_contact_id"], "789")
        self.contact_request.assert_called_with("test", "/crm/v4/objects/contacts/789/associations/default/companies/123", method="PUT")

    @patch("sales.hubspot_request")
    @patch("sales.ensure_domain_key")
    def test_creates_missing_company_after_domain_search(self, ensure, request):
        request.side_effect = [{"results": []}, {"status":"COMPLETE","results":[{"id":"456","new":True}]}]
        draft, = build_drafts([self.record], token="test")
        self.assertEqual(draft["hubspot_company_id"], "456")
        ensure.assert_called_once_with("test")
        path, payload = request.call_args.args[1:]
        self.assertEqual(path, "/batch/upsert")
        self.assertEqual(payload["inputs"][0]["idProperty"], "ai_business_os_domain")
        self.assertEqual(payload["inputs"][0]["id"], "example.com")

    @patch("sales.hubspot_request")
    def test_rejects_non_matching_contact_without_crm_write(self, request):
        self.record["generic_contact_emails"] = ["export@other.example"]
        self.assertEqual(build_drafts([self.record], token="test"), [])
        request.assert_not_called()
        self.contact_request.assert_not_called()
