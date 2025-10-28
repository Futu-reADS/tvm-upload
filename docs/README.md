# TVM Upload System - Documentation

Welcome to the TVM Upload System documentation! This directory contains comprehensive guides for testing, deployment, and operations.

## 📚 Documentation Index

### Core Documentation

| Document | Purpose | Target Audience | Time to Read |
|----------|---------|----------------|--------------|
| **[quick_start.md](./quick_start.md)** | 5-minute vehicle deployment guide | Deployment Technicians | 5 min |
| **[deployment_guide.md](./deployment_guide.md)** | Complete deployment guide | Operators, DevOps | 30 min |
| **[complete_reference.md](./complete_reference.md)** | Comprehensive feature reference & examples | All Users | 60 min |

### Testing Documentation

| Document | Purpose | Target Audience | Time to Read |
|----------|---------|----------------|--------------|
| **[testing_strategy_overview.md](./testing_strategy_overview.md)** | High-level testing strategy & philosophy | Tech Leads, Architects | 15 min |
| **[manual_testing_guide.md](./manual_testing_guide.md)** | Step-by-step manual testing procedures | QA Engineers, Operators | 30 min |
| **[autonomous_testing_guide.md](./autonomous_testing_guide.md)** | Automated testing architecture & execution | Developers, DevOps | 20 min |

### CI/CD Documentation

| Document | Purpose | Target Audience | Time to Read |
|----------|---------|----------------|--------------|
| **[github_actions_oidc_setup.md](./github_actions_oidc_setup.md)** | AWS OIDC setup for GitHub Actions | DevOps, Security Team | 45 min |

### Quick Navigation

**🎯 I want to...**

| Task | Document | Section |
|------|----------|---------|
| Deploy to a vehicle quickly | [quick_start.md](./quick_start.md) | Full guide |
| Set up OIDC for GitHub Actions | [github_actions_oidc_setup.md](./github_actions_oidc_setup.md) | Step-by-step |
| Understand testing approach | [testing_strategy_overview.md](./testing_strategy_overview.md) | Full document |
| Manually test the system | [manual_testing_guide.md](./manual_testing_guide.md) | Feature Tests |
| Run automated tests locally | [autonomous_testing_guide.md](./autonomous_testing_guide.md) | Test Execution |
| Deploy to production | [deployment_guide.md](./deployment_guide.md) | Full guide |
| Troubleshoot OIDC issues | [github_actions_oidc_setup.md](./github_actions_oidc_setup.md) | Troubleshooting |

---

## 🚀 Quick Start

### For Developers

**1. Run tests before committing:**
```bash
# Fast check (< 30 seconds)
./scripts/testing/quick_check.sh

# Full local tests (< 2 minutes)
pytest tests/unit/ tests/integration/ -v
```

**2. Check coverage:**
```bash
./scripts/testing/test_coverage.sh
```

**3. Push code:**
```bash
git push origin feature-branch
# GitHub Actions will auto-run all tests
```

### For QA Engineers

**1. Follow manual testing guide:**
```bash
# Start here
cat docs/manual_testing_guide.md

# Run tests sequentially (12 tests, ~2 hours)
```

**2. Fill out test report template:**
```markdown
See: manual_testing_guide.md
Section: "Manual Testing Summary Report Template"
```

### For DevOps/SRE

**1. Review CI/CD pipeline:**
```bash
cat docs/autonomous_testing_guide.md
# Section: "CI/CD Pipeline"
```

**2. Configure GitHub Actions:**
```bash
# File: .github/workflows/tests.yml
# Already configured! Just verify secrets:
# - AWS_ROLE_ARN
# - TEST_BUCKET
```

---

## 📊 Testing Summary

### Test Coverage

```
Total Tests: 180+
├── Unit Tests:        100+  (Fast, Isolated)
├── Integration Tests:  20   (Component Interactions)
└── E2E Tests:          60   (Real AWS)

Code Coverage: 90%+
CI/CD: ✅ Automated via GitHub Actions
```

### Test Execution Times

| Test Type | Count | Avg Time/Test | Total Time |
|-----------|-------|---------------|------------|
| Unit | 100+ | < 1s | ~1 min |
| Integration | 20 | ~2s | ~1 min |
| E2E | 60 | ~7s | ~7 min |
| **Total** | **180+** | **-** | **~10 min** |

---

## 🎯 Testing Philosophy

We follow the **Test Pyramid** approach:

```
           /\
          /  \     E2E (10%)
         /────\    Real AWS, Slow, High Confidence
        /      \
       /────────\  Integration (20%)
      /          \ Mocked AWS, Medium Speed
     /────────────\
    /              \ Unit (70%)
   /────────────────\ No Deps, Fast, Immediate Feedback
```

**Key Principles:**
1. **Fast Feedback:** Unit tests run in < 1 second
2. **High Coverage:** 90%+ code coverage
3. **Real Validation:** E2E tests use actual AWS
4. **Automated:** Tests run on every commit
5. **Maintainable:** Clear, well-documented tests

---

## 📖 Document Descriptions

### testing_strategy_overview.md
**Purpose:** Strategic view of our testing approach

**Contents:**
- Executive summary
- Manual vs Autonomous comparison
- Recommended workflows
- Key insights & recommendations
- Test metrics dashboard
- Future enhancements

**Best for:**
- Understanding the big picture
- Making strategic decisions
- Planning improvements
- Reviewing test strategy

---

### manual_testing_guide.md
**Purpose:** Hands-on guide for manual testing

**Contents:**
- 12 comprehensive test scenarios
- Step-by-step instructions
- Expected results & success criteria
- Troubleshooting guide
- Test report template

**Best for:**
- QA engineers
- First-time deployment
- Customer acceptance testing
- Investigating production issues

**Test Scenarios:**
1. Basic File Upload
2. Source-Based Path Detection
3. File Date Preservation
4. CloudWatch Metrics Publishing
5. CloudWatch Alarm Creation
6. Duplicate Upload Prevention
7. Disk Space Management
8. Batch Upload Performance
9. Large File Upload (Multipart)
10. Error Handling and Retry
11. Operational Hours Compliance
12. Service Restart Resilience

---

### autonomous_testing_guide.md
**Purpose:** Complete guide to automated testing

**Contents:**
- Test pyramid architecture
- All 180+ test descriptions
- CI/CD pipeline configuration
- Test execution scripts
- Coverage analysis
- Performance metrics

**Best for:**
- Developers writing tests
- DevOps setting up CI/CD
- Understanding test architecture
- Debugging test failures

**Test Categories:**
- 20 File Monitor tests
- 30 Upload Manager tests
- 15 Disk Manager tests
- 20 S3 Uploader tests
- 15 CloudWatch Manager tests
- 20 Integration scenarios
- 60 E2E workflows

---

## 🛠️ Test Execution Scripts

### Quick Reference

```bash
# Run all tests
./scripts/testing/run_tests.sh all

# Run specific type
./scripts/testing/run_tests.sh unit
./scripts/testing/run_tests.sh integration
./scripts/testing/run_tests.sh e2e

# Coverage report
./scripts/testing/test_coverage.sh

# Pre-commit check
./scripts/testing/quick_check.sh
```

### Detailed Usage

**Local Development:**
```bash
# Fastest feedback (unit only)
pytest tests/unit/ -v

# Local validation (unit + integration)
pytest tests/unit/ tests/integration/ -v

# Full suite (includes real AWS)
pytest tests/e2e/ -v -m e2e
```

**CI/CD:**
```bash
# GitHub Actions auto-runs on push
# See: .github/workflows/tests.yml

# Manual trigger:
gh workflow run tests.yml
```

---

## 🔍 Finding What You Need

### Common Questions

**Q: How do I test before deploying to production?**
→ See: [manual_testing_guide.md](./manual_testing_guide.md)

**Q: What tests exist and what do they cover?**
→ See: [autonomous_testing_guide.md](./autonomous_testing_guide.md) - Test Categories

**Q: How is our testing strategy different from others?**
→ See: [testing_strategy_overview.md](./testing_strategy_overview.md) - My Analysis

**Q: How do I add a new test?**
→ See: [autonomous_testing_guide.md](./autonomous_testing_guide.md) - Test Pyramid Architecture

**Q: Tests are failing, what do I do?**
→ See: [manual_testing_guide.md](./manual_testing_guide.md) - Troubleshooting

**Q: What's the ROI of our testing investment?**
→ See: [testing_strategy_overview.md](./testing_strategy_overview.md) - Success Metrics

---

## 📈 Test Metrics

### Current Status (As of 2025-01-27)

| Metric | Value | Status |
|--------|-------|--------|
| Unit Tests | 100+ | ✅ |
| Integration Tests | 20 | ✅ |
| E2E Tests | 60 | ✅ |
| Code Coverage | 90%+ | ✅ |
| PR Test Time | ~2 min | ✅ |
| Full Suite Time | ~10 min | ✅ |
| Flaky Tests | 0 | ✅ |
| Security Scans | 0 | ⚠️ Need to add |

### Quality Trends

```
Jan 2025: ████████░░ 85% coverage → Added 30 unit tests
          ██████████ 90% coverage → Added 20 integration tests
          ██████████ 90% coverage → Added 60 E2E tests ✅
```

---

## 🤝 Contributing

### Adding Documentation

**When to update docs:**
- New test added → Update autonomous_testing_guide.md
- New manual test scenario → Update manual_testing_guide.md
- Testing strategy change → Update testing_strategy_overview.md

**How to update:**
1. Edit relevant markdown file
2. Update version number at bottom
3. Update "Last Updated" date
4. Submit PR with changes

### Improving Tests

**Guidelines:**
1. Follow existing test patterns
2. Add docstrings explaining what you're testing
3. Ensure tests are fast (< 5s for unit tests)
4. Clean up test resources (use fixtures)
5. Maintain > 90% coverage

---

## 📞 Getting Help

**Questions about testing?**
- Read the appropriate guide above
- Check GitHub Discussions
- Ask in team Slack: #tvm-upload

**Found an issue?**
- File a bug report
- Include test logs
- Describe expected vs actual behavior

**Want to contribute?**
- Read CONTRIBUTING.md (project root)
- Follow test patterns
- Submit PR with tests

---

## 📅 Maintenance Schedule

### Weekly
- Review failed tests in CI/CD
- Check coverage trends
- Update flaky test list

### Monthly
- Full test suite review
- Documentation updates
- Performance benchmarking

### Quarterly
- Strategy review
- Tool updates (pytest, boto3, etc.)
- Test refactoring

---

## 🔗 Related Resources

**Project Documentation:**
- [Main README](../README.md) - Project overview
- [CONFIG.md](./CONFIG.md) - Configuration guide
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Deployment guide

**External Resources:**
- [pytest Documentation](https://docs.pytest.org/)
- [boto3 Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
- [GitHub Actions](https://docs.github.com/en/actions)

---

**Last Updated:** 2025-01-27
**Maintained By:** TVM Upload Team
**Review Cycle:** Monthly
