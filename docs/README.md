# TVM Upload System - Documentation

Welcome to the TVM Upload System documentation! This directory contains comprehensive guides for testing, deployment, and operations.

## 📚 Documentation Index

### Testing Documentation

| Document | Purpose | Target Audience | Time to Read |
|----------|---------|----------------|--------------|
| **[TESTING_STRATEGY_OVERVIEW.md](./TESTING_STRATEGY_OVERVIEW.md)** | High-level testing strategy, my thoughts & recommendations | Tech Leads, Architects | 15 min |
| **[MANUAL_TESTING_GUIDE.md](./MANUAL_TESTING_GUIDE.md)** | Step-by-step manual testing procedures | QA Engineers, Operators | 30 min |
| **[AUTONOMOUS_TESTING_GUIDE.md](./AUTONOMOUS_TESTING_GUIDE.md)** | Automated testing architecture & execution | Developers, DevOps | 20 min |

### Quick Navigation

**🎯 I want to...**

| Task | Document | Section |
|------|----------|---------|
| Understand overall testing approach | [TESTING_STRATEGY_OVERVIEW.md](./TESTING_STRATEGY_OVERVIEW.md) | Full document |
| Manually test the system before deployment | [MANUAL_TESTING_GUIDE.md](./MANUAL_TESTING_GUIDE.md) | Feature Testing Sequence |
| Run automated tests locally | [AUTONOMOUS_TESTING_GUIDE.md](./AUTONOMOUS_TESTING_GUIDE.md) | Test Execution Scripts |
| Set up CI/CD pipeline | [AUTONOMOUS_TESTING_GUIDE.md](./AUTONOMOUS_TESTING_GUIDE.md) | CI/CD Pipeline |
| Check test coverage | [AUTONOMOUS_TESTING_GUIDE.md](./AUTONOMOUS_TESTING_GUIDE.md) | Coverage Analysis |
| Troubleshoot test failures | [MANUAL_TESTING_GUIDE.md](./MANUAL_TESTING_GUIDE.md) | Troubleshooting |
| Add new tests | [AUTONOMOUS_TESTING_GUIDE.md](./AUTONOMOUS_TESTING_GUIDE.md) | Test Pyramid Architecture |

---

## 🚀 Quick Start

### For Developers

**1. Run tests before committing:**
```bash
# Fast check (< 30 seconds)
./scripts/quick_check.sh

# Full local tests (< 2 minutes)
pytest tests/unit/ tests/integration/ -v
```

**2. Check coverage:**
```bash
./scripts/test_coverage.sh
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
cat docs/MANUAL_TESTING_GUIDE.md

# Run tests sequentially (12 tests, ~2 hours)
```

**2. Fill out test report template:**
```markdown
See: MANUAL_TESTING_GUIDE.md
Section: "Manual Testing Summary Report Template"
```

### For DevOps/SRE

**1. Review CI/CD pipeline:**
```bash
cat docs/AUTONOMOUS_TESTING_GUIDE.md
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

### TESTING_STRATEGY_OVERVIEW.md
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

### MANUAL_TESTING_GUIDE.md
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

### AUTONOMOUS_TESTING_GUIDE.md
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
./scripts/run_tests.sh all

# Run specific type
./scripts/run_tests.sh unit
./scripts/run_tests.sh integration
./scripts/run_tests.sh e2e

# Coverage report
./scripts/test_coverage.sh

# Pre-commit check
./scripts/quick_check.sh
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
→ See: [MANUAL_TESTING_GUIDE.md](./MANUAL_TESTING_GUIDE.md)

**Q: What tests exist and what do they cover?**
→ See: [AUTONOMOUS_TESTING_GUIDE.md](./AUTONOMOUS_TESTING_GUIDE.md) - Test Categories

**Q: How is our testing strategy different from others?**
→ See: [TESTING_STRATEGY_OVERVIEW.md](./TESTING_STRATEGY_OVERVIEW.md) - My Analysis

**Q: How do I add a new test?**
→ See: [AUTONOMOUS_TESTING_GUIDE.md](./AUTONOMOUS_TESTING_GUIDE.md) - Test Pyramid Architecture

**Q: Tests are failing, what do I do?**
→ See: [MANUAL_TESTING_GUIDE.md](./MANUAL_TESTING_GUIDE.md) - Troubleshooting

**Q: What's the ROI of our testing investment?**
→ See: [TESTING_STRATEGY_OVERVIEW.md](./TESTING_STRATEGY_OVERVIEW.md) - Success Metrics

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
- New test added → Update AUTONOMOUS_TESTING_GUIDE.md
- New manual test scenario → Update MANUAL_TESTING_GUIDE.md
- Testing strategy change → Update TESTING_STRATEGY_OVERVIEW.md

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
