import unittest
from unittest.mock import patch

from sales import build_drafts


class SalesPipelineTests(unittest.TestCase):
    def setUp(self):
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

    @patch("sales.hubspot_request")
    def test_creates_missing_company_after_domain_search(self, request):
        request.side_effect = [{"results": []}, {"id": "456"}]
        draft, = build_drafts([self.record], token="test")
        self.assertEqual(draft["hubspot_company_id"], "456")
        request.assert_called_with("test", "", {"properties": {"name": "Example", "domain": "example.com"}})

    @patch("sales.hubspot_request")
    def test_rejects_non_matching_contact_without_crm_write(self, request):
        self.record["generic_contact_emails"] = ["export@other.example"]
        self.assertEqual(build_drafts([self.record], token="test"), [])
        request.assert_not_called()
