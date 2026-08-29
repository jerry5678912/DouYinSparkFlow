import json
import logging
import unittest

from utils.logger import JsonFormatter, setup_logger


class LoggerTests(unittest.TestCase):
    def tearDown(self):
        logger = logging.getLogger('test-logger')
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)

    def test_setup_logger_updates_existing_handler_levels(self):
        logger = setup_logger(name='test-logger', level='Info')
        self.assertEqual([handler.level for handler in logger.handlers], [logging.INFO, logging.INFO])

        logger = setup_logger(name='test-logger', level='Debug')

        self.assertEqual(logger.level, logging.DEBUG)
        self.assertEqual([handler.level for handler in logger.handlers], [logging.DEBUG, logging.DEBUG])

    def test_json_formatter_emits_allowlisted_reliability_fields_only(self):
        record = logging.LogRecord(
            name="test-logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=42,
            msg="delivery verified",
            args=(),
            exc_info=None,
        )
        record.event = "message_send_verified"
        record.run_id = "run-123"
        record.verified_count = 1
        record.cookie = "must-not-be-logged"

        payload = json.loads(JsonFormatter().format(record))

        self.assertEqual(payload["event"], "message_send_verified")
        self.assertEqual(payload["run_id"], "run-123")
        self.assertEqual(payload["verified_count"], 1)
        self.assertNotIn("cookie", payload)
        self.assertNotIn("must-not-be-logged", json.dumps(payload))

    def test_setup_logger_uses_structured_json_formatters(self):
        logger = setup_logger(name="test-logger", level="Info")

        self.assertTrue(
            all(isinstance(handler.formatter, JsonFormatter) for handler in logger.handlers)
        )


if __name__ == '__main__':
    unittest.main()
