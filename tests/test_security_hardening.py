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
        self.assertIn("wz.json", ignored_patterns)
        self.assertIn("gsy.json", ignored_patterns)

    def test_configuration_generator_is_documented_as_local_only(self):
        instructions = (
            REPOSITORY_ROOT / "docs" / "配置生成器使用.md"
        ).read_text(encoding="utf-8")

        self.assertIn("http://127.0.0.1:8765/", instructions)
        self.assertNotIn("oilu.cn", instructions)

    def test_runtime_has_no_unused_openai_integration(self):
        tasks_source = (REPOSITORY_ROOT / "core" / "tasks.py").read_text(
            encoding="utf-8"
        )
        message_builder_source = (
            REPOSITORY_ROOT / "core" / "msg_builder.py"
        ).read_text(encoding="utf-8")
        requirements = (REPOSITORY_ROOT / "requirements.txt").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("build_message_with_openai", tasks_source)
        self.assertNotIn("build_message_with_openai", message_builder_source)
        self.assertNotIn("openai==", requirements)

    def test_container_runs_as_non_root_user(self):
        dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("chown -R pwuser:pwuser /app", dockerfile)
        self.assertIn("USER pwuser", dockerfile)

    def test_legacy_cron_helper_does_not_copy_the_whole_environment(self):
        entrypoint = (REPOSITORY_ROOT / "docker" / "entrypoint.sh").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("merged_vars", entrypoint)
        self.assertIn("chmod 0600 /etc/douyin-spark-flow.env", entrypoint)
        self.assertIn("must be an integer", entrypoint)
        self.assertIn('re.fullmatch(r"[A-Z_][A-Z0-9_]*", key)', entrypoint)

    def test_runtime_logs_do_not_include_message_or_recipient_identifiers(self):
        tasks_source = (REPOSITORY_ROOT / "core" / "tasks.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("目标好友列表: {targets}", tasks_source)
        self.assertNotIn("找到好友 {targetName}", tasks_source)
        self.assertNotIn("消息模板:", tasks_source)
        self.assertNotIn("目标好友: {user['targets']}", tasks_source)
        self.assertNotIn("开始处理账号 {username}", tasks_source)


if __name__ == "__main__":
    unittest.main()
