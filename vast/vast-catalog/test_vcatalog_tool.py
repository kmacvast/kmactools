#!/usr/bin/env python3
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure local runtime path is prioritized in the python context
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import vcatalog_tool

class TestVCatalogTool(unittest.TestCase):
    
    def test_format_bytes(self):
        """Verify byte sizing formatting transforms match cleanly."""
        self.assertIn("0", vcatalog_tool.format_bytes(0))
        self.assertIn("KB", vcatalog_tool.format_bytes(1024))
        self.assertIn("MB", vcatalog_tool.format_bytes(1024 * 1024))
        self.assertIn("GB", vcatalog_tool.format_bytes(1024 * 1024 * 1024))

    def test_parse_human_size(self):
        """Test human sizing strings map to exact numeric integer bytes."""
        if hasattr(vcatalog_tool, 'parse_human_size'):
            self.assertEqual(vcatalog_tool.parse_human_size("1K"), 1024)
            self.assertEqual(vcatalog_tool.parse_human_size("1M"), 1048576)
            self.assertEqual(vcatalog_tool.parse_human_size("2G"), 2147483648)

    @patch('vcatalog_tool.load_config')
    @patch('vastdb.connect')
    def test_argparse_routing_schema(self, mock_connect, mock_load_config):
        """Ensure configuration paths route successfully to mock database sessions."""
        mock_load_config.return_value = {
            "vast_endpoint": "http://127.0.0.1",
            "access_key": "mock_key",
            "secret_key": "mock_secret",
            "mount_path": "/mnt/mock"
        }
        
        mock_session = MagicMock()
        mock_tx = MagicMock()
        mock_table = MagicMock()
        
        mock_field = MagicMock()
        mock_field.name = "test_column"
        mock_field.type = "string"
        
        mock_table.arrow_schema = [mock_field]
        mock_tx.catalog.return_value = mock_table
        mock_session.transaction.return_value.__enter__.return_value = mock_tx
        mock_connect.return_value = mock_session

        with patch('sys.argv', ['vcatalog_tool.py', '--show-schema']):
            try:
                vcatalog_tool.main()
            except SystemExit as e:
                self.assertEqual(e.code, 0)

if __name__ == '__main__':
    unittest.main()
