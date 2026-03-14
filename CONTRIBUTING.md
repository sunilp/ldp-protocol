# Contributing to LDP

Thanks for your interest in contributing to the LLM Delegate Protocol.

## Getting Started

### Prerequisites

- Rust 1.75+ (for the reference implementation)
- Python 3.10+ (for the Python SDK examples)

### Building

```bash
cargo build
cargo test
```

### Python examples

```bash
cd examples/python_sdk
pip install -r requirements.txt
python ldp_delegate.py   # Terminal 1
python ldp_client.py     # Terminal 2
```

## How to Contribute

### Good First Issues

Look for issues labeled [`good first issue`](../../labels/good%20first%20issue) — these are scoped, well-defined tasks suitable for newcomers.

### Types of Contributions

- **Bug reports** — Open an issue with reproduction steps
- **Bug fixes** — PRs welcome, please reference the issue
- **Documentation** — Improvements to README, RFC, or inline docs
- **Tests** — Additional test cases, especially for edge cases
- **SDK ports** — Implementations in new languages
- **Examples** — New usage examples or tutorials

### Pull Request Process

1. Fork the repo and create a branch from `main`
2. Make your changes with clear commit messages
3. Add or update tests if applicable
4. Ensure `cargo test` passes
5. Open a PR with a description of what and why

### Code Style

- Rust: follow `rustfmt` defaults (`cargo fmt`)
- Python: follow PEP 8
- Keep PRs focused — one concern per PR

## Protocol Contributions

For changes to the protocol specification itself (docs/RFC.md), please open an issue first to discuss the proposed change. Protocol changes require careful consideration of backward compatibility and interoperability.

## Questions?

Open a [Discussion](../../discussions) for questions, ideas, or general conversation about LDP.

## License

By contributing, you agree that your contributions will be licensed under the Apache-2.0 License.
