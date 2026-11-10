# {{PROJECT_NAME}}

> Language-agnostic starter. Use it for Go, Rust, C#, Java or anything else.

## First steps

1. Set up your language's project in `src/` (e.g. `go mod init`, `cargo init`, `dotnet new`).
2. Fill in the commands in `scripts/check.sh`. CI runs this file.
3. Fill in the TODOs in `CLAUDE.md`, so the AI agents know how to build and test.
4. If CI needs a toolchain, add a `setup-command` in `.github/workflows/ci.yml`.

```bash
bash scripts/check.sh   # run all checks locally
```

## Development workflow

This project uses the [software-factory](https://github.com/{{GITHUB_OWNER}}/software-factory) pipeline:

```
/factory-build <feature>   plan → build → test → review → docs
/factory-ship              push and open a pull request
```
