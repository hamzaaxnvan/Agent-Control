module.exports = {
  branches: ["main"],
  tagFormat: "ts-sdk-v${version}",
  plugins: [
    [
      "@semantic-release/commit-analyzer",
      {
        preset: "conventionalcommits",
        releaseRules: [
          { breaking: true, release: "major" },
          { type: "feat", scope: "sdk-ts", release: "minor" },
          { type: "fix", scope: "sdk-ts", release: "patch" },
          { type: "perf", scope: "sdk-ts", release: "patch" },
          { type: "refactor", scope: "sdk-ts", release: "patch" },
          { type: "chore", scope: "sdk-ts", release: "patch" },
        ],
      },
    ],
    [
      "@semantic-release/release-notes-generator",
      {
        preset: "conventionalcommits",
      },
