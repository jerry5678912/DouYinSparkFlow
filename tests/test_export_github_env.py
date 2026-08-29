from io import StringIO
import unittest

from utils.export_github_env import append_github_env_block, validate_env_key


class ExportGithubEnvTests(unittest.TestCase):
    def test_environment_keys_must_use_portable_safe_characters(self):
        self.assertEqual(validate_env_key("SAFE_KEY_1"), "SAFE_KEY_1")

        for unsafe_key in ("BAD-KEY", "BAD\nINJECTED", "1BAD", "BAD=VALUE"):
            with self.subTest(unsafe_key=unsafe_key):
                with self.assertRaises(ValueError):
                    validate_env_key(unsafe_key)

    def test_multiline_delimiter_never_collides_with_value(self):
        value = "first\n__ENV_EOF__\nlast"
        output = StringIO()

        append_github_env_block(output, "SAFE_KEY", value)

        first_line = output.getvalue().splitlines()[0]
        delimiter = first_line.split("<<", 1)[1]
        self.assertNotIn(delimiter, value.splitlines())
        self.assertIn(value, output.getvalue())


if __name__ == "__main__":
    unittest.main()
