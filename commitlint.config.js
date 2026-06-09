// commitlint — enforces Conventional Commits (drives release-please/semantic-release).
// Install: npm i -D @commitlint/cli @commitlint/config-conventional
// Wire via lefthook (commit-msg) or the conventional-pre-commit hook in pre-commit.
export default {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "type-enum": [
      2,
      "always",
      [
        "feat",
        "fix",
        "docs",
        "style",
        "refactor",
        "perf",
        "test",
        "build",
        "ci",
        "chore",
        "revert",
      ],
    ],
    "subject-case": [2, "never", ["upper-case", "pascal-case", "start-case"]],
    "body-max-line-length": [1, "always", 100],
  },
};
