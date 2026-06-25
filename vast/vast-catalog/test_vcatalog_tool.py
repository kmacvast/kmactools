#!/usr/bin/env python3
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import vcatalog_tool

class TestVCatalogToolExtended(unittest.TestCase):

    def test_format_bytes(self):
        """Verify byte sizing formatting transforms match cleanly."""
        self.assertEqual(vcatalog_tool.format_bytes(0), "0.00 B")
        self.assertIn("KB", vcatalog_tool.format_bytes(1024))
        self.assertIn("MB", vcatalog_tool.format_bytes(1024 * 1024))
        self.assertIn("GB", vcatalog_tool.format_bytes(1024 * 1024 * 1024))

    def test_parse_human_size(self):
        """Test human sizing strings map to exact numeric integer bytes."""
        if hasattr(vcatalog_tool, 'parse_human_size'):
            self.assertEqual(vcatalog_tool.parse_human_size("4K"), 4096)
            self.assertEqual(vcatalog_tool.parse_human_size("10M"), 10485760)
            self.assertEqual(vcatalog_tool.parse_human_size("1G"), 1073741824)

    def test_cross_protocol_translation_logic(self):
        """Ensure local path structures resolve perfectly to catalog and S3 coordinate sets."""
        if hasattr(vcatalog_tool, 'translate_path_logic'):
            mock_config = {
                "mount_path": "/mnt/kmacs-root/vast-catalog",
                "catalog_prefix": "/kmacs/vast-catalog",
                "s3_bucket": "kmacs-vast-catalog-test-bucket"
            }
            input_path = "/mnt/kmacs-root/vast-catalog/workspace_1/test_image.JPEG"
            paths = vcatalog_tool.translate_path_logic(input_path, mock_config)
            
            self.assertEqual(paths['nfs'], "/mnt/kmacs-root/vast-catalog/workspace_1/test_image.JPEG")
            self.assertEqual(paths['catalog'], "/kmacs/vast-catalog/workspace_1/test_image.JPEG")
            self.assertEqual(paths['s3'], "s3://kmacs-vast-catalog-test-bucket/workspace_1/test_image.JPEG")

    def test_data_reduction_rate_calculations(self):
        """Verify the multi-pillar reduction weight distribution functions execute correctly."""
        if hasattr(vcatalog_tool, 'calculate_reduction_breakdown'):
            logical_bytes = 100_000_000
            physical_bytes = 20_000_000 # 5:1 reduction ratio / 80% space saved
            
            metrics = vcatalog_tool.calculate_reduction_breakdown(logical_bytes, physical_bytes)
            self.assertAlmostEqual(metrics['ratio'], 5.0, places=2)
            self.assertAlmostEqual(metrics['net_saved_pct'], 80.0, places=2)
            self.assertAlmostEqual(metrics['dedup_pct'], 32.0, places=2)      # 40% of 80%
            self.assertAlmostEqual(metrics['similarity'], 28.0, places=2)     # 35% of 80%
            self.assertAlmostEqual(metrics['compression'], 20.0, places=2)    # 25% of 80%

    @patch('vcatalog_tool.load_config')
    @patch('vastdb.connect')
    def test_argparse_routing_schema(self, mock_connect, mock_load_config):
        """Ensure schema commands parse and interact safely with mocked db session objects."""
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
