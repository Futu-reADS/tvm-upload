# AWS OIDC Authentication for GitHub Actions

**Complete Step-by-Step Setup Guide**

---

## ✅ Setup Status

**Current Status:** ✅ Complete (January 2025)
**Tested With:**
- AWS Region: cn-north-1 (Beijing)
- GitHub Actions: ubuntu-latest
- Python: 3.10+
- boto3: 1.34.x

**Last Verified:** January 2025

---

## 🚀 Quick Reference (For Experienced Users)

Already familiar with OIDC? Here's the TL;DR:

### AWS Setup (5 minutes)

1. **IAM → Identity providers → Add OIDC provider**
   - Provider URL: `https://token.actions.githubusercontent.com`
   - Audience: `sts.amazonaws.com`

2. **IAM → Roles → Create role (Web identity)**
   - Trust policy: Allow repo `{ORG}/{REPO}:*`
   - Attach minimal permissions policy

3. **Copy Role ARN**

### GitHub Workflow

```yaml
permissions:
  id-token: write
  contents: read

- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws-cn:iam::{ACCOUNT_ID}:role/{ROLE_NAME}
    aws-region: cn-north-1
```

### Generic IAM Policy Template

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetObject", "s3:PutObject"],
      "Resource": [
        "arn:aws-cn:s3:::{BUCKET_NAME}",
        "arn:aws-cn:s3:::{BUCKET_NAME}/*"
      ]
    },
    {
      "Sid": "CloudWatchAccess",
      "Effect": "Allow",
      "Action": "cloudwatch:PutMetricData",
      "Resource": "*"
    }
  ]
}
```

**For detailed setup, continue reading below.**

---

## 🔧 Generic Template (For Any Repository)

Replace these placeholders with your values:

| Placeholder | Description | Example |
|------------|-------------|---------|
| `{ACCOUNT_ID}` | Your AWS Account ID | `621346161733` |
| `{GITHUB_ORG}` | GitHub organization name | `Futu-reADS` |
| `{GITHUB_REPO}` | Repository name | `tvm-upload` |
| `{BUCKET_NAME}` | S3 bucket name | `t01logs` |
| `{REGION}` | AWS region | `cn-north-1` |
| `{ROLE_NAME}` | IAM role name | `GitHubActions-E2E-Role` |

---

## 📖 Related Documentation

**This guide:** First-time OIDC setup (one-time, 30-45 minutes)
**For daily usage:** See [AUTONOMOUS_TESTING_GUIDE.md](./AUTONOMOUS_TESTING_GUIDE.md)

**When to use which:**
- **Use this guide:** Setting up OIDC for a NEW repository or troubleshooting OIDC issues
- **Use testing guide:** Running tests with existing OIDC setup

---

## 📋 Table of Contents

1. [Overview & Benefits](#overview--benefits)
2. [Prerequisites](#prerequisites)
3. [Part 1: Create OIDC Identity Provider](#part-1-create-oidc-identity-provider)
4. [Part 2: Create IAM Role](#part-2-create-iam-role)
5. [Part 3: Add Permissions](#part-3-add-permissions)
6. [Part 4: Update GitHub Workflow](#part-4-update-github-workflow)
7. [Part 5: Fix Test Code](#part-5-fix-test-code)
8. [Troubleshooting](#troubleshooting)
9. [Verification](#verification)

---

## 🎯 Overview & Benefits

### What is OIDC?

OpenID Connect (OIDC) allows GitHub Actions to authenticate with AWS **without storing long-lived credentials**. GitHub requests a temporary token from AWS, which expires automatically.

### Why Use OIDC?

| Aspect | Traditional (Access Keys) | OIDC (Modern) |
|--------|--------------------------|---------------|
| **Security** | ⚠️ Keys last forever | ✅ Tokens expire in hours |
| **Storage** | ⚠️ Stored in GitHub Secrets | ✅ No secrets stored |
| **Rotation** | ⚠️ Manual every 90 days | ✅ Automatic |
| **Leak Risk** | ⚠️ High (if leaked, valid forever) | ✅ Low (expires quickly) |
| **Audit Trail** | ⚠️ Limited | ✅ Full CloudTrail logs |
| **Maintenance** | ⚠️ High | ✅ Zero |
| **Industry Practice** | ⚠️ Outdated | ✅ Best practice |

### What You'll Accomplish

By the end, GitHub Actions will be able to:
- ✅ Authenticate to AWS automatically
- ✅ Access S3 buckets
- ✅ Publish CloudWatch metrics
- ✅ Run E2E tests against real AWS
- ✅ All without any secrets stored in GitHub!

---

## 🔑 Prerequisites

Before starting, ensure you have:

- [ ] AWS Console access with IAM permissions
- [ ] GitHub repository with admin access
- [ ] S3 bucket created (if needed)
- [ ] 30-45 minutes of focused time

---

## 📝 Part 1: Create OIDC Identity Provider

### Step 1.1: Navigate to Identity Providers

```
AWS Console
  ↓
Search for "IAM" (top search bar)
  ↓
Click "IAM" (Identity and Access Management)
  ↓
Left sidebar → Click "Identity providers"
  ↓
Click "Add provider" button
```

**⚠️ Common Mistake:** Don't go to "Roles" first - you need Identity providers!

---

### Step 1.2: Select Provider Type

On the "Add Identity provider" page:

**❌ DO NOT select "SAML"** - This is wrong!

**✅ SELECT "OpenID Connect"** - This is correct!

---

### Step 1.3: Fill Provider Details

| Field | Value | Notes |
|-------|-------|-------|
| **Provider URL** | `https://token.actions.githubusercontent.com` | Exact URL, no trailing slash |
| **Audience** | `sts.amazonaws.com` | Standard value for GitHub Actions |

**⚠️ Important:** Copy these EXACTLY - no spaces, no extra characters!

---

### Step 1.4: Get Thumbprint

After entering the Provider URL, click the **"Get thumbprint"** button.

- AWS will automatically fetch and verify the thumbprint
- Wait a few seconds for it to complete
- You should see a thumbprint value appear

**✅ Success indicator:** Thumbprint field populates automatically

---

### Step 1.5: Name the Provider (Optional)

In the **Provider name** field, enter:
```
GitHub-Actions-OIDC
```

**Note:** This is optional but recommended for clarity.

---

### Step 1.6: Add Provider

1. Skip "Add tags" section (optional)
2. Click the orange **"Add provider"** button at bottom right
3. Wait for success message

**✅ Success:** You'll see a green banner saying "Identity provider created successfully"

---

### Step 1.7: Copy Provider ARN

After creation, you'll see the provider details page. **COPY** the Provider ARN (you'll see your account ID):

```
arn:aws-cn:iam::{ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com
```

**💾 Save this!** You'll need it later (though not critical - AWS will show it when needed).

---

## 🔐 Part 2: Create IAM Role

### Step 2.1: Start Role Creation

```
IAM Dashboard
  ↓
Left sidebar → Click "Roles"
  ↓
Click "Create role" button (top right)
```

---

### Step 2.2: Select Trusted Entity Type

On "Select trusted entity" page:

**✅ SELECT:** "Web identity"

**You should see:**
- Identity provider dropdown
- Audience dropdown
- Additional options

**⚠️ DO NOT select:**
- ❌ AWS service
- ❌ AWS account
- ❌ Custom trust policy
- ❌ SAML 2.0 federation

---

### Step 2.3: Configure Web Identity

Fill in the dropdowns:

| Field | Value | How to Find |
|-------|-------|-------------|
| **Identity provider** | `token.actions.githubusercontent.com` | Select from dropdown (the one you just created) |
| **Audience** | `sts.amazonaws.com` | Select from dropdown |

**✅ Verification:** Both fields should auto-populate from your OIDC provider.

---

### Step 2.4: Add GitHub Organization/Repository Condition

This is **CRITICAL for security** - it restricts which GitHub repos can use this role.

Click **"Add condition"** or look for the condition section.

**⚠️ IMPORTANT: Fill These Fields EXACTLY Right!**

#### Common Mistakes

**❌ WRONG FORMAT (What NOT to do):**
```
GitHub organization: repo:YourOrg/your-repo     ← WRONG! No "repo:" prefix
GitHub organization: YourOrg/your-repo          ← WRONG! No repo name
GitHub repository: https://github.com/YourOrg/your-repo  ← WRONG! No URL
```

**✅ CORRECT FORMAT:**

| Field | Exact Value | Explanation |
|-------|-------------|-------------|
| **GitHub organization** | `{GITHUB_ORG}` | Just the org name, nothing else |
| **GitHub repository** | `{GITHUB_REPO}` | Just the repo name, nothing else |
| **GitHub branch** | `*` or `main` | `*` = all branches, `main` = main only |

**Example:**
- Organization: `Futu-reADS`
- Repository: `tvm-upload`
- Branch: `*` (all branches)

**Error you'll see if wrong:** *"The field 'GitHub organization' has characters that aren't valid: :,/"*

---

### Step 2.5: Review Trust Policy

After adding conditions, you should see a trust policy preview like:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws-cn:iam::{ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:{GITHUB_ORG}/{GITHUB_REPO}:*"
        }
      }
    }
  ]
}
```

**✅ Verify:**
- Federated ARN matches your provider
- Repo name is correct

Click **"Next"** to continue.

---

## 🔓 Part 3: Add Permissions

### Step 3.1: Understand the Permissions Screen

You'll see a page titled "Add permissions" with 541+ AWS managed policies.

**⚠️ CRITICAL: DO NOT SELECT ANY OF THESE!**

Policies like:
- ❌ AdministratorAccess - Way too much access!
- ❌ AmazonS3FullAccess - Access to ALL buckets!
- ❌ CloudWatchFullAccess - More than needed!

**Why not?** These give far more permissions than needed. We'll create a custom minimal policy.

---

### Step 3.2: Skip Managed Policies

**Option A: If you see "Create policy" button**
1. Click **"Create policy"** button (opens new tab)
2. Jump to Step 3.3

**Option B: If you don't see "Create policy" button**
1. Don't select any policies
2. Click **"Next"** at bottom
3. Continue to Step 2.6 (Name the role)
4. We'll add permissions AFTER creating the role

**💡 Tip:** Option B is actually easier - create role first, add permissions second.

---

### Step 3.3: Create Custom Inline Policy

If you opened "Create policy" in new tab:

1. Click **"JSON"** tab (not "Visual")
2. Delete everything in the editor
3. Paste this policy (adjust for your needs):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3BucketAccess",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws-cn:s3:::{BUCKET_NAME}"
    },
    {
      "Sid": "S3ObjectAccess",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws-cn:s3:::{BUCKET_NAME}/*"
    },
    {
      "Sid": "CloudWatchMetrics",
      "Effect": "Allow",
      "Action": "cloudwatch:PutMetricData",
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "cloudwatch:namespace": "TVM/Upload"
        }
      }
    },
    {
      "Sid": "CloudWatchAlarms",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricAlarm",
        "cloudwatch:DeleteAlarms",
        "cloudwatch:DescribeAlarms"
      ],
      "Resource": "arn:aws-cn:cloudwatch:{REGION}:{ACCOUNT_ID}:alarm:TVM-*"
    }
  ]
}
```

**Replace placeholders:**
- `{BUCKET_NAME}` → Your S3 bucket
- `{REGION}` → Your AWS region
- `{ACCOUNT_ID}` → Your AWS account ID

4. Click **"Next"**
5. **Policy name:** `GitHubActions-E2E-MinimalPolicy`
6. **Description:** `Minimal permissions for GitHub Actions E2E tests`
7. Click **"Create policy"**
8. Go back to role creation tab
9. Click refresh icon ↻
10. Search for `GitHubActions-E2E-MinimalPolicy`
11. Check the box next to it
12. Click **"Next"**

---

### Step 2.6: Name the Role

On the "Name, review, and create" page:

| Field | Value |
|-------|-------|
| **Role name** | `{ROLE_NAME}` (e.g., `GitHubActions-E2E-Role`) |
| **Description** | `OIDC role for GitHub Actions with minimal permissions` |

---

### Step 2.7: Review and Create

Review the summary:

- ✅ **Trusted entities:** Should show Web identity with GitHub
- ✅ **Trust policy:** Should show repo condition
- ⚠️ **Permissions:** May be empty (we'll add after if using Option B)
- ✅ **Tags:** Optional, can skip

**Click the orange "Create role" button!**

---

### Step 2.8: Success! Copy Role ARN

After creation, you'll see the role details page.

**At the top, you'll see the Role ARN:**

```
arn:aws-cn:iam::{ACCOUNT_ID}:role/{ROLE_NAME}
```

**💾 CRITICAL: COPY THIS ARN!**

You'll need it for the GitHub workflow. Save it somewhere!

---

### Step 3.4: Add Permissions After Creation (If Option B)

If you skipped permissions earlier, add them now:

1. You should be on the role details page
2. Click **"Permissions"** tab
3. Click **"Add permissions"** dropdown
4. Select **"Create inline policy"**
5. Click **"JSON"** tab
6. Paste the policy from Step 3.3
7. Click **"Review policy"**
8. **Name:** `E2E-Test-Minimal-Permissions`
9. Click **"Create policy"**

**✅ Done!** Role now has the necessary permissions.

---

## 🔄 Part 4: Update GitHub Workflow

### Step 4.1: Locate Workflow File

In your repository:
```
.github/
  └── workflows/
      └── test-e2e.yml  (or your workflow file)
```

---

### Step 4.2: Update Workflow

Add these sections to your workflow:

```yaml
name: E2E Tests (Real AWS - OIDC)

on:
  push:
    branches: [main]
  workflow_dispatch:

# ✅ NEW: Required for OIDC authentication
permissions:
  id-token: write  # Required to request OIDC token
  contents: read   # Required to checkout code

jobs:
  e2e-tests:
    name: E2E Tests
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      # ✅ NEW: OIDC authentication (no secrets!)
      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws-cn:iam::{ACCOUNT_ID}:role/{ROLE_NAME}
          # ↑ REPLACE with YOUR Role ARN from Step 2.8!
          aws-region: {REGION}

      - name: Run E2E tests
        env:
          TEST_BUCKET: {BUCKET_NAME}
          AWS_REGION: {REGION}
        run: |
          pytest tests/e2e/ -v
```

**⚠️ CRITICAL:** Replace all placeholders with your actual values!

---

### Step 4.3: Key Changes Explained

| What Changed | Before | After |
|--------------|--------|-------|
| **Permissions** | Not specified | `id-token: write` added |
| **Authentication** | Used access keys | Uses OIDC role |
| **Secrets** | Required 2-3 secrets | Zero secrets! |
| **Maintenance** | Rotate keys every 90 days | Zero maintenance |

---

## 🧪 Part 5: Fix Test Code

### Step 5.1: Update E2E Test Fixtures

**File:** `tests/e2e/conftest.py`

The issue: Tests may be hardcoded to use AWS profile, which doesn't exist in GitHub Actions.

**Update your fixtures to handle both local (with profile) and CI (with OIDC):**

```python
import pytest
import boto3
import os

@pytest.fixture(scope='session')
def aws_config():
    """
    AWS configuration - works locally and in CI/CD
    """
    return {
        'profile': os.getenv('AWS_PROFILE', None),  # None in CI, profile name locally
        'bucket': os.getenv('TEST_BUCKET', '{BUCKET_NAME}'),
        'region': os.getenv('AWS_REGION', '{REGION}'),
        'vehicle_id': 'e2e-test-vehicle'
    }

@pytest.fixture
def real_s3_client(aws_config):
    """
    REAL S3 client - handles both local and CI/CD
    """
    if aws_config['profile']:
        # Local: Use profile
        session = boto3.Session(
            profile_name=aws_config['profile'],
            region_name=aws_config['region']
        )
    else:
        # CI/CD: Use OIDC credentials (no profile)
        session = boto3.Session(region_name=aws_config['region'])

    return session.client('s3')
```

**Key concept:**
- Local: `AWS_PROFILE=china` → Uses profile
- CI/CD: `AWS_PROFILE` not set → Uses OIDC credentials

---

### Step 5.2: Commit and Push

```bash
# Stage changes
git add .github/workflows/
git add tests/e2e/conftest.py

# Commit
git commit -m "Setup OIDC authentication for GitHub Actions"

# Push to main
git push origin main
```

---

## 🔍 Troubleshooting

### Issue 1: "Login with Amazon" Appears Instead of OIDC

**Problem:** You're in the wrong section of AWS Console.

**Solution:**
```
✅ CORRECT PATH:
IAM → Identity providers → Add provider → OpenID Connect

❌ WRONG PATH:
IAM → Roles → Create role → SAML 2.0 federation
```

---

### Issue 2: "GitHub organization has invalid characters"

**Problem:** Wrong format in GitHub organization field.

**Correct format:**
```
✅ Organization: YourOrg
✅ Repository: your-repo
✅ Branch: main or *
```

---

### Issue 3: "Profile not found" in E2E Tests

**Problem:** Test fixtures still using hardcoded profile.

**Solution:** Update `tests/e2e/conftest.py` as shown in Step 5.1.

**Verify fix:**
```bash
grep "AWS_PROFILE" tests/e2e/conftest.py
# Should show: 'profile': os.getenv('AWS_PROFILE', None),
```

---

### Issue 4: "AccessDenied" in E2E Tests

**Problem:** IAM role missing required permissions.

**Solution:** Add the missing permission to your IAM role policy (Step 3.3).

---

### Issue 5: "Could not assume role" in GitHub Actions

**Problem:** Trust policy doesn't allow your GitHub repo.

**Check trust policy:**
1. Go to IAM Role
2. Click "Trust relationships" tab
3. Verify repo name in condition

**Fix:** Edit trust policy to add/correct repo condition.

---

## ✅ Verification

### Step V.1: Verify IAM Setup

**Check OIDC Provider:**
```
AWS Console → IAM → Identity providers
Should see: token.actions.githubusercontent.com
```

**Check IAM Role:**
```
AWS Console → IAM → Roles → {ROLE_NAME}

Trust relationships tab:
  ✅ Federated: token.actions.githubusercontent.com
  ✅ Condition: repo:{GITHUB_ORG}/{GITHUB_REPO}:*

Permissions tab:
  ✅ Custom policy attached
```

---

### Step V.2: Test GitHub Workflow

**Manual trigger:**
```
GitHub → Your repo → Actions tab → Your workflow → Run workflow
```

**Expected logs:**
```
Configure AWS credentials (OIDC)
  ✅ Assuming role: {ROLE_NAME}
  ✅ Role assumed successfully

Run E2E tests
  ✅ Tests running with temporary credentials
```

---

### Step V.3: Verify No Secrets Stored

```
GitHub → Your repo → Settings → Secrets and variables → Actions

Expected:
  - Should NOT have AWS_ACCESS_KEY_ID
  - Should NOT have AWS_SECRET_ACCESS_KEY

If these exist from before, you can DELETE them now! 🎉
```

---

### Step V.4: Test Locally

Ensure local development still works:

```bash
# Set profile for local testing
export AWS_PROFILE=your-profile-name

# Run E2E tests
pytest tests/e2e/ -v

# Should use profile (not OIDC)
```

---

## 📊 Before & After Comparison

### Security

| Aspect | Before (Access Keys) | After (OIDC) |
|--------|---------------------|--------------|
| Credentials stored | ⚠️ In GitHub Secrets | ✅ None |
| Credential lifetime | ⚠️ Forever | ✅ Hours |
| Rotation needed | ⚠️ Every 90 days | ✅ Automatic |
| If leaked | ⚠️ Valid until rotated | ✅ Expires quickly |
| Audit trail | ⚠️ Limited | ✅ Full CloudTrail |
| Best practice | ❌ No | ✅ Yes |

### Maintenance

| Task | Before | After |
|------|--------|-------|
| Initial setup | 5 minutes | 30-45 minutes |
| Monthly maintenance | 15 minutes | 0 minutes |
| Key rotation | Required | Not needed |
| **Annual effort** | **~3 hours** | **~30 minutes** |

---

## 📝 Summary Checklist

After completing this guide, you should have:

- [ ] OIDC Identity Provider created in AWS
- [ ] IAM Role created with GitHub trust policy
- [ ] Minimal permissions policy attached to role
- [ ] Role ARN copied and saved
- [ ] GitHub workflow updated to use OIDC
- [ ] Test fixtures updated to handle None profile
- [ ] Changes committed and pushed
- [ ] E2E tests passing in GitHub Actions
- [ ] No AWS secrets stored in GitHub
- [ ] Local development still working with profile

---

## 🎯 What You've Achieved

1. ✅ **Most secure** method for GitHub-to-AWS authentication
2. ✅ **Zero secrets** stored anywhere
3. ✅ **Zero maintenance** - no key rotation needed
4. ✅ **Production-grade** security following AWS best practices
5. ✅ **Audit trail** - every action logged in CloudTrail
6. ✅ **Temporary credentials** - tokens expire automatically

### Time Investment

- **Setup:** 30-45 minutes (one-time)
- **Maintenance:** 0 minutes/month forever
- **ROI:** Excellent - saves time and improves security

### Next Steps

1. Delete old AWS access key secrets from GitHub (if any)
2. Apply same pattern to other projects/repos
3. Document this setup for your team

---

## 📚 Additional Resources

**AWS Documentation:**
- [Using OIDC with GitHub Actions](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html)
- [IAM Roles Terms and Concepts](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_terms-and-concepts.html)

**GitHub Documentation:**
- [Configuring OIDC in AWS](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [Security hardening for GitHub Actions](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)

**Best Practices:**
- [AWS Security Best Practices](https://aws.amazon.com/architecture/security-identity-compliance/)
- [Principle of Least Privilege](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html#grant-least-privilege)

---

## 💬 Support

If you encounter issues:

1. Check the [Troubleshooting](#troubleshooting) section
2. Verify each step was completed exactly as written
3. Check AWS CloudTrail logs for detailed error messages
4. Review GitHub Actions logs for authentication issues

---

**Document Version:** 2.0
**Last Updated:** January 2025
**Status:** Production Ready ✅
**Author:** Futu-reADS DevOps Team
**Project:** TVM Upload System (Reference Implementation)
