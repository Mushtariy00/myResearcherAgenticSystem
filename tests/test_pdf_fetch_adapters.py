"""Unit tests for PDF fetch adapters (Unpaywall, OpenAlex, waterfall)."""
from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from agentic_ai_system.tools.paper_fetch_tools import (
    _get_openalex_pdf_url,
    _get_unpaywall_pdf_url,
    resolve_pdf_url_waterfall,
)


class TestUnpaywallAdapter(unittest.TestCase):
    """Test Unpaywall API adapter."""

    @patch("urllib.request.urlopen")
    def test_unpaywall_with_valid_doi(self, mock_urlopen):
        """Test Unpaywall lookup with valid DOI returns PDF URL."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "is_oa": True,
            "best_oa_location": {
                "url_for_pdf": "https://example.com/paper.pdf",
                "url": "https://example.com/paper"
            }
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = _get_unpaywall_pdf_url("10.1234/example.doi")
        self.assertEqual(result, "https://example.com/paper.pdf")

    @patch("urllib.request.urlopen")
    def test_unpaywall_fallback_to_url(self, mock_urlopen):
        """Test Unpaywall falls back to url field if url_for_pdf missing."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "is_oa": True,
            "best_oa_location": {
                "url": "https://example.com/paper"
            }
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = _get_unpaywall_pdf_url("10.1234/example.doi")
        self.assertEqual(result, "https://example.com/paper")

    @patch("urllib.request.urlopen")
    def test_unpaywall_not_open_access(self, mock_urlopen):
        """Test Unpaywall returns None if paper is not OA."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "is_oa": False,
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = _get_unpaywall_pdf_url("10.1234/example.doi")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_unpaywall_network_error(self, mock_urlopen):
        """Test Unpaywall returns None on network error."""
        mock_urlopen.side_effect = Exception("Network error")

        result = _get_unpaywall_pdf_url("10.1234/example.doi")
        self.assertIsNone(result)

    def test_unpaywall_empty_doi(self):
        """Test Unpaywall returns None with empty DOI."""
        result = _get_unpaywall_pdf_url("")
        self.assertIsNone(result)

    def test_unpaywall_none_doi(self):
        """Test Unpaywall returns None with None DOI."""
        result = _get_unpaywall_pdf_url(None)
        self.assertIsNone(result)


class TestOpenAlexAdapter(unittest.TestCase):
    """Test OpenAlex API adapter."""

    @patch("urllib.request.urlopen")
    def test_openalex_with_valid_doi(self, mock_urlopen):
        """Test OpenAlex lookup with valid DOI returns OA URL."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "results": [{
                "open_access": {
                    "oa_url": "https://openalex.org/works/paper.pdf",
                    "is_oa": True
                }
            }]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = _get_openalex_pdf_url(doi="10.1234/example.doi")
        self.assertEqual(result, "https://openalex.org/works/paper.pdf")

    @patch("urllib.request.urlopen")
    def test_openalex_fallback_to_oa_location(self, mock_urlopen):
        """Test OpenAlex falls back to oa_location if oa_url missing."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "results": [{
                "open_access": {
                    "is_oa": True,
                    "oa_location": {
                        "url_for_pdf": "https://example.com/paper.pdf"
                    }
                }
            }]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = _get_openalex_pdf_url(doi="10.1234/example.doi")
        self.assertEqual(result, "https://example.com/paper.pdf")

    @patch("urllib.request.urlopen")
    def test_openalex_no_results(self, mock_urlopen):
        """Test OpenAlex returns None when no results."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "results": []
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = _get_openalex_pdf_url(doi="10.1234/example.doi")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_openalex_not_oa(self, mock_urlopen):
        """Test OpenAlex returns None if work is not OA."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "results": [{
                "open_access": {
                    "is_oa": False
                }
            }]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = _get_openalex_pdf_url(doi="10.1234/example.doi")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_openalex_network_error(self, mock_urlopen):
        """Test OpenAlex returns None on network error."""
        mock_urlopen.side_effect = Exception("Network error")

        result = _get_openalex_pdf_url(doi="10.1234/example.doi")
        self.assertIsNone(result)

    def test_openalex_empty_doi_and_title(self):
        """Test OpenAlex returns None with no DOI or title."""
        result = _get_openalex_pdf_url(doi=None, title=None)
        self.assertIsNone(result)


class TestPDFWaterfall(unittest.TestCase):
    """Test PDF URL waterfall resolution strategy."""

    @patch("agentic_ai_system.tools.paper_fetch_tools._resolve_arxiv_pdf_url")
    def test_waterfall_arxiv_first(self, mock_arxiv):
        """Test waterfall tries arXiv first."""
        mock_arxiv.return_value = "https://arxiv.org/pdf/2101.00001.pdf"

        result = resolve_pdf_url_waterfall(
            source_url="https://arxiv.org/abs/2101.00001",
            doi="10.1234/example",
            title="Example Paper"
        )
        self.assertEqual(result, "https://arxiv.org/pdf/2101.00001.pdf")
        mock_arxiv.assert_called_once()

    @patch("agentic_ai_system.tools.paper_fetch_tools._resolve_arxiv_pdf_url")
    @patch("agentic_ai_system.tools.paper_fetch_tools._get_unpaywall_pdf_url")
    def test_waterfall_unpaywall_second(self, mock_unpaywall, mock_arxiv):
        """Test waterfall falls to Unpaywall when arXiv fails."""
        mock_arxiv.return_value = None
        mock_unpaywall.return_value = "https://unpaywall.org/paper.pdf"

        result = resolve_pdf_url_waterfall(
            source_url="https://example.com/paper",
            doi="10.1234/example",
            title="Example Paper"
        )
        self.assertEqual(result, "https://unpaywall.org/paper.pdf")

    @patch("agentic_ai_system.tools.paper_fetch_tools._resolve_arxiv_pdf_url")
    @patch("agentic_ai_system.tools.paper_fetch_tools._get_unpaywall_pdf_url")
    @patch("agentic_ai_system.tools.paper_fetch_tools._get_openalex_pdf_url")
    def test_waterfall_openalex_third(self, mock_openalex, mock_unpaywall, mock_arxiv):
        """Test waterfall falls to OpenAlex when arXiv and Unpaywall fail."""
        mock_arxiv.return_value = None
        mock_unpaywall.return_value = None
        mock_openalex.return_value = "https://openalex.org/paper.pdf"

        result = resolve_pdf_url_waterfall(
            source_url="https://example.com/paper",
            doi="10.1234/example",
            title="Example Paper"
        )
        self.assertEqual(result, "https://openalex.org/paper.pdf")

    @patch("agentic_ai_system.tools.paper_fetch_tools._resolve_arxiv_pdf_url")
    @patch("agentic_ai_system.tools.paper_fetch_tools._get_unpaywall_pdf_url")
    @patch("agentic_ai_system.tools.paper_fetch_tools._get_openalex_pdf_url")
    @patch("agentic_ai_system.tools.paper_fetch_tools._resolve_html_pdf_url")
    def test_waterfall_html_fourth(self, mock_html, mock_openalex, mock_unpaywall, mock_arxiv):
        """Test waterfall falls to HTML parsing when all others fail."""
        mock_arxiv.return_value = None
        mock_unpaywall.return_value = None
        mock_openalex.return_value = None
        mock_html.return_value = "https://example.com/paper.pdf"

        result = resolve_pdf_url_waterfall(
            source_url="https://example.com/paper",
            doi="10.1234/example",
            title="Example Paper"
        )
        self.assertEqual(result, "https://example.com/paper.pdf")

    @patch("agentic_ai_system.tools.paper_fetch_tools._resolve_arxiv_pdf_url")
    @patch("agentic_ai_system.tools.paper_fetch_tools._get_unpaywall_pdf_url")
    @patch("agentic_ai_system.tools.paper_fetch_tools._get_openalex_pdf_url")
    @patch("agentic_ai_system.tools.paper_fetch_tools._resolve_html_pdf_url")
    def test_waterfall_all_fail(self, mock_html, mock_openalex, mock_unpaywall, mock_arxiv):
        """Test waterfall returns None when all strategies fail."""
        mock_arxiv.return_value = None
        mock_unpaywall.return_value = None
        mock_openalex.return_value = None
        mock_html.return_value = None

        result = resolve_pdf_url_waterfall(
            source_url="https://example.com/paper",
            doi="10.1234/example",
            title="Example Paper"
        )
        self.assertIsNone(result)

    @patch("agentic_ai_system.tools.paper_fetch_tools._resolve_arxiv_pdf_url")
    def test_waterfall_skips_unpaywall_without_doi(self, mock_arxiv):
        """Test waterfall skips Unpaywall if no DOI provided."""
        mock_arxiv.return_value = None

        with patch("agentic_ai_system.tools.paper_fetch_tools._get_unpaywall_pdf_url") as mock_unpaywall:
            with patch("agentic_ai_system.tools.paper_fetch_tools._get_openalex_pdf_url") as mock_openalex:
                mock_openalex.return_value = None
                with patch("agentic_ai_system.tools.paper_fetch_tools._resolve_html_pdf_url") as mock_html:
                    mock_html.return_value = None

                    result = resolve_pdf_url_waterfall(
                        source_url="https://example.com/paper",
                        doi=None,
                        title="Example Paper"
                    )
                    mock_unpaywall.assert_not_called()


if __name__ == "__main__":
    unittest.main()
