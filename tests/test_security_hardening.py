from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class SecurityHardeningTests(unittest.TestCase):
    def test_configuration_details_never_render_untrusted_html(self):
        generator_source = (
            REPOSITORY_ROOT / "docs" / "static" / "js" / "main.js"
        ).read_text(encoding="utf-8")

        self.assertNotIn("dangerouslyUseHTMLString: true", generator_source)
        self.assertNotIn('"value:",\n        value', generator_source)

    def test_local_configuration_and_secret_files_are_gitignored(self):
        ignored_patterns = set(
            (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        )

        self.assertIn("config/", ignored_patterns)
        self.assertIn("*.env", ignored_patterns)
        self.assertIn("*.pem", ignored_patterns)
        self.assertIn("*.key", ignored_patterns)


if __name__ == "__main__":
    unittest.main()
