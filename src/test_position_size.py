import unittest
import position_size

class TestPositionSize(unittest.TestCase):
    def test_creation(self):
        current = { 'BTC': 1 }
        future = { 'BTC': 1, 'ETH': 2 }
        expected = { 'ETH': 2 }
        self.assertEqual(expected, position_size.get_order_sizes(current, future))

    def test_resolution(self):
        current = { 'BTC': 1, 'ETH': 2 }
        future = { 'BTC': 1 }
        expected = { 'ETH': -2 }
        self.assertEqual(expected, position_size.get_order_sizes(current, future))

    def test_change(self):
        current = { 'BTC': 1, 'ETH': 2 }
        future = { 'BTC': 2, 'ETH': 1 }
        expected = { 'BTC': 1, 'ETH': -1 }
        self.assertEqual(expected, position_size.get_order_sizes(current, future))

if __name__ == '__main__':
    unittest.main()
