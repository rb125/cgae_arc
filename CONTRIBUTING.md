# Contributing to CGAE

Thanks for your interest! This project is part of the Arc × Circle Hackathon submission.

## Getting Started

1. Fork the repo and clone locally
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   npm install
   ```
3. Copy `.env.example` to `.env` and fill in your credentials
4. Run tests: `npx hardhat test`

## Development Workflow

- Create a feature branch from `main`
- Write tests for new functionality
- Ensure `npx hardhat test` passes
- Submit a PR with a clear description

## Code Style

- **Python**: Follow PEP 8
- **Solidity**: Follow the [Solidity Style Guide](https://docs.soliditylang.org/en/latest/style-guide.html)
- **TypeScript**: Prettier defaults (via Hardhat)

## Reporting Issues

Open a GitHub issue with:
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Node/Python version)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
