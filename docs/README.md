# TVM Upload System - Documentation

Welcome to the TVM Upload System documentation! This directory contains guides for deployment, testing, and operations.

---

## 📚 Documentation Index

### Core Documentation

| Document | Purpose | Target Audience |
|----------|---------|-----------------|
| **[deployment_guide.md](./deployment_guide.md)** | **START HERE** - Step-by-step vehicle deployment with automated scripts | Operators, DevOps |
| **[complete_reference.md](./complete_reference.md)** | Comprehensive feature reference, configuration options, and examples | All Users |

### Testing Documentation

| Document | Purpose | Target Audience |
|----------|---------|-----------------|
| **[testing_strategy_overview.md](./testing_strategy_overview.md)** | High-level testing strategy and philosophy | Tech Leads, Architects |
| **[manual_testing_guide.md](./manual_testing_guide.md)** | 16 automated manual test scenarios with step-by-step procedures | QA Engineers |
| **[autonomous_testing_guide.md](./autonomous_testing_guide.md)** | 277 automated tests (159 unit + 42 integration + 60 E2E + 16 manual) | Developers, DevOps |

### CI/CD Documentation

| Document | Purpose | Target Audience |
|----------|---------|-----------------|
| **[github_actions_oidc_setup.md](./github_actions_oidc_setup.md)** | AWS OIDC setup for GitHub Actions (no stored credentials) | DevOps, Security |

---

## 🎯 Quick Navigation

**I want to...**

| Task | Go to |
|------|-------|
| Deploy the system to a vehicle | [deployment_guide.md](./deployment_guide.md) |
| Understand all features and configuration | [complete_reference.md](./complete_reference.md) |
| Run manual tests before production | [manual_testing_guide.md](./manual_testing_guide.md) |
| Run automated tests locally | [autonomous_testing_guide.md](./autonomous_testing_guide.md) |
| Set up CI/CD with GitHub Actions | [github_actions_oidc_setup.md](./github_actions_oidc_setup.md) |
| Review testing strategy | [testing_strategy_overview.md](./testing_strategy_overview.md) |

---

## 📊 Quick Facts

**System Overview:**
- Total automated tests: 277 (159 unit + 42 integration + 60 E2E + 16 manual, 90%+ code coverage)
- Manual test scenarios: 16 comprehensive automated scenarios (~24 min runtime)
- Deployment time: ~5-10 minutes per vehicle
- Supports: AWS China region (cn-north-1, cn-northwest-1)

**Key Scripts:**
- `./scripts/deployment/install.sh` - Automated installation
- `./scripts/deployment/verify_deployment.sh` - Pre-deployment validation
- `./scripts/deployment/health_check.sh` - System health verification
- `./scripts/diagnostics/verify_aws_credentials.sh` - AWS credentials check

---

## 🚀 Getting Started

### For Operators/DevOps
1. Read [deployment_guide.md](./deployment_guide.md)
2. Follow the 9-step deployment process
3. Use health check scripts to verify installation

### For Developers
1. Read [complete_reference.md](./complete_reference.md) for architecture
2. Read [autonomous_testing_guide.md](./autonomous_testing_guide.md) for testing
3. Run tests: `./scripts/testing/run_tests.sh`

### For QA Engineers
1. Read [manual_testing_guide.md](./manual_testing_guide.md)
2. Execute 16 automated test scenarios using `scripts/testing/run_manual_tests.sh`
3. Fill out test report template

---

## 📞 Support

**Questions?**
- Check the relevant guide above
- Review main [README.md](../README.md)
- Check GitHub Issues: https://github.com/Futu-reADS/tvm-upload/issues

---

**Last Updated:** 2025-11-05
**Maintained By:** TVM Upload Team
