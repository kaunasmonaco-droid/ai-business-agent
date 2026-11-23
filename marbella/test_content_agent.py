import json
import unittest
from content_agent import plan

class PlannerTests(unittest.TestCase):
    def test_seven_safe_drafts(self):
        items=plan({"account":"@elitemarbella_cars","start_date":"2026-11-23"})
        self.assertEqual(len(items),7)
        self.assertEqual(items[0]["date"],"2026-11-23")
        for item in items:
            self.assertEqual(item["publication_status"],"DRAFT_NOT_PUBLISHED")
            self.assertFalse(item["payment_requested"])
            self.assertTrue(item["requires_human_approval"])
            self.assertEqual(item["price_claim"],"none")
            self.assertEqual(item["availability_claim"],"none")
    def test_no_other_accounts(self):
        with self.assertRaises(ValueError):
            plan({"account":"@other_account","start_date":"2026-11-23"})

if __name__ == "__main__":
    unittest.main()
