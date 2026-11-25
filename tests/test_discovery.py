import unittest
from unittest.mock import patch

from main import run


class DiscoveryTests(unittest.TestCase):
    @patch("main.find_websites")
    def test_checks_one_site_per_domain_and_preserves_provenance(self, find):
        find.return_value = iter([
            ("http://www.example.lt", "Example Works", "https://www.openstreetmap.org/node/2"),
            ("https://example.lt/contact", "Duplicate", "https://www.openstreetmap.org/node/3"),
        ])
        records = run(
            {"discovery_country": "LT", "keywords": ["metal"]},
            fetcher=lambda url: (url, "<title>Example</title>We manufacture sheet metal. sales@example.lt"),
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source_url"], "https://www.example.lt")
        self.assertEqual(records[0]["company_name"], "Example Works")
        self.assertEqual(records[0]["discovery_source_url"], "https://www.openstreetmap.org/node/2")
        self.assertEqual(records[0]["generic_contact_emails"], ["sales@example.lt"])
