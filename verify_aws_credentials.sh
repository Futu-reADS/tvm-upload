#!/bin/bash
# AWS Credentials Verification Script
# Tests S3 and CloudWatch access for China region

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     AWS Credentials Verification for TVM Upload               ║"
echo "╔════════════════════════════════════════════════════════════════╗"
echo ""

# Load config
REGION="cn-north-1"
BUCKET="t01logs"
PROFILE="china"
VEHICLE_ID="vehicle-CN-001"

echo "Configuration:"
echo "  Region:     $REGION"
echo "  Bucket:     $BUCKET"
echo "  Profile:    $PROFILE"
echo "  Vehicle ID: $VEHICLE_ID"
echo ""

# Test 1: Check AWS CLI
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 1: AWS CLI Installation"
echo "═══════════════════════════════════════════════════════════════"
if command -v aws >/dev/null 2>&1; then
    AWS_VERSION=$(aws --version 2>&1)
    echo "✓ AWS CLI installed: $AWS_VERSION"
else
    echo "✗ AWS CLI not found!"
    echo "  Install with: sudo apt install awscli"
    exit 1
fi
echo ""

# Test 2: Check credentials file
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 2: AWS Credentials Configuration"
echo "═══════════════════════════════════════════════════════════════"
CREDS_FILE="$HOME/.aws/credentials"
CONFIG_FILE="$HOME/.aws/config"

if [ -f "$CREDS_FILE" ]; then
    echo "✓ Credentials file exists: $CREDS_FILE"
    if grep -q "\[${PROFILE}\]" "$CREDS_FILE"; then
        echo "✓ Profile '$PROFILE' found in credentials"
    else
        echo "✗ Profile '$PROFILE' NOT found in credentials"
        echo "  Available profiles:"
        grep "^\[" "$CREDS_FILE" || echo "  (none)"
    fi
else
    echo "✗ Credentials file not found: $CREDS_FILE"
    exit 1
fi

if [ -f "$CONFIG_FILE" ]; then
    echo "✓ Config file exists: $CONFIG_FILE"
    if grep -q "\[profile ${PROFILE}\]" "$CONFIG_FILE"; then
        echo "✓ Profile '$PROFILE' found in config"
    else
        echo "⚠ Profile '$PROFILE' NOT found in config (may be optional)"
    fi
else
    echo "⚠ Config file not found: $CONFIG_FILE (may be optional)"
fi
echo ""

# Test 3: Verify AWS identity
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 3: AWS Identity Verification"
echo "═══════════════════════════════════════════════════════════════"
echo "Running: aws sts get-caller-identity --profile $PROFILE --region $REGION"
if IDENTITY=$(aws sts get-caller-identity --profile "$PROFILE" --region "$REGION" 2>&1); then
    echo "✓ AWS credentials valid!"
    echo "$IDENTITY" | python3 -m json.tool 2>/dev/null || echo "$IDENTITY"
else
    echo "✗ AWS credentials INVALID!"
    echo "Error: $IDENTITY"
    echo ""
    echo "This means your AWS credentials are expired or incorrect."
    echo "Please update ~/.aws/credentials with valid credentials."
    exit 1
fi
echo ""

# Test 4: S3 Access
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 4: S3 Bucket Access"
echo "═══════════════════════════════════════════════════════════════"
echo "Running: aws s3 ls s3://$BUCKET --profile $PROFILE --region $REGION"
if S3_RESULT=$(aws s3 ls "s3://${BUCKET}" --profile "$PROFILE" --region "$REGION" 2>&1); then
    echo "✓ S3 bucket accessible!"
    echo "  Bucket contents (first 10 items):"
    echo "$S3_RESULT" | head -10 | sed 's/^/  /'

    # Count items
    ITEM_COUNT=$(echo "$S3_RESULT" | wc -l)
    echo "  Total items in bucket: $ITEM_COUNT"
else
    echo "✗ S3 bucket NOT accessible!"
    echo "Error: $S3_RESULT"
    echo ""
    echo "Required S3 permissions:"
    echo "  - s3:ListBucket"
    echo "  - s3:GetObject"
    echo "  - s3:PutObject"
    exit 1
fi
echo ""

# Test 5: S3 Write Permission (test upload)
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 5: S3 Write Permission"
echo "═══════════════════════════════════════════════════════════════"
TEST_FILE="/tmp/aws-test-$(date +%s).txt"
TEST_KEY="${VEHICLE_ID}/test/aws-credential-test-$(date +%s).txt"

echo "Test content - $(date)" > "$TEST_FILE"
echo "Running: aws s3 cp $TEST_FILE s3://$BUCKET/$TEST_KEY"

if aws s3 cp "$TEST_FILE" "s3://${BUCKET}/${TEST_KEY}" --profile "$PROFILE" --region "$REGION" >/dev/null 2>&1; then
    echo "✓ S3 upload successful!"

    # Verify file exists
    if aws s3 ls "s3://${BUCKET}/${TEST_KEY}" --profile "$PROFILE" --region "$REGION" >/dev/null 2>&1; then
        echo "✓ Test file verified in S3"

        # Clean up
        aws s3 rm "s3://${BUCKET}/${TEST_KEY}" --profile "$PROFILE" --region "$REGION" >/dev/null 2>&1
        echo "✓ Test file cleaned up"
    fi
else
    echo "✗ S3 upload FAILED!"
    echo "  Required permission: s3:PutObject"
    exit 1
fi

rm -f "$TEST_FILE"
echo ""

# Test 6: CloudWatch Metrics Access
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 6: CloudWatch Metrics Access"
echo "═══════════════════════════════════════════════════════════════"
echo "Running: aws cloudwatch list-metrics --namespace TVM/Upload"

if CW_RESULT=$(aws cloudwatch list-metrics --namespace "TVM/Upload" --profile "$PROFILE" --region "$REGION" 2>&1); then
    echo "✓ CloudWatch list-metrics permission OK"

    METRIC_COUNT=$(echo "$CW_RESULT" | grep -c "MetricName" || echo "0")
    echo "  Existing TVM metrics: $METRIC_COUNT"
else
    echo "⚠ CloudWatch list-metrics failed (may be permission issue)"
    echo "  Error: $CW_RESULT"
fi
echo ""

# Test 7: CloudWatch Put Metric Data
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 7: CloudWatch Put Metric Permission"
echo "═══════════════════════════════════════════════════════════════"
echo "Running: aws cloudwatch put-metric-data (test metric)"

PUT_RESULT=$(aws cloudwatch put-metric-data \
    --namespace "TVM/Upload" \
    --metric-name "TestMetric" \
    --value 1.0 \
    --dimensions VehicleId="${VEHICLE_ID}",TestType=CredentialVerification \
    --profile "$PROFILE" \
    --region "$REGION" 2>&1)

if [ $? -eq 0 ]; then
    echo "✓ CloudWatch put-metric-data permission OK"
    echo "✓ Can publish metrics to CloudWatch"
else
    echo "✗ CloudWatch put-metric-data FAILED!"
    echo "  Error: $PUT_RESULT"
    echo ""
    echo "  Required permission: cloudwatch:PutMetricData"
    echo ""
    echo "  CloudWatch tests will be SKIPPED unless this is fixed."
    CLOUDWATCH_OK="false"
fi
echo ""

# Test 8: CloudWatch Alarms
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 8: CloudWatch Alarms Access"
echo "═══════════════════════════════════════════════════════════════"
echo "Running: aws cloudwatch describe-alarms"

if ALARM_RESULT=$(aws cloudwatch describe-alarms --alarm-name-prefix "TVM-" --profile "$PROFILE" --region "$REGION" 2>&1); then
    echo "✓ CloudWatch describe-alarms permission OK"

    ALARM_COUNT=$(echo "$ALARM_RESULT" | grep -c "AlarmName" || echo "0")
    echo "  Existing TVM alarms: $ALARM_COUNT"
else
    echo "⚠ CloudWatch describe-alarms failed"
    echo "  Error: $ALARM_RESULT"
fi
echo ""

# Summary
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     VERIFICATION SUMMARY                                       ║"
echo "╔════════════════════════════════════════════════════════════════╗"
echo ""

if [ "${CLOUDWATCH_OK:-true}" = "true" ]; then
    echo "✓ ALL TESTS PASSED!"
    echo ""
    echo "Your AWS credentials are fully configured and working."
    echo "You can now:"
    echo "  1. Re-enable CloudWatch in config/config.yaml"
    echo "  2. Run the full manual test suite"
    echo ""
    echo "To re-enable CloudWatch:"
    echo "  sed -i 's/cloudwatch_enabled: false/cloudwatch_enabled: true/' config/config.yaml"
    echo ""
    echo "To run tests:"
    echo "  ./scripts/run_manual_tests.sh"
    exit 0
else
    echo "⚠ PARTIAL SUCCESS - S3 works, CloudWatch needs attention"
    echo ""
    echo "What works:"
    echo "  ✓ AWS credentials are valid"
    echo "  ✓ S3 bucket is accessible"
    echo "  ✓ Can upload files to S3"
    echo ""
    echo "What needs fixing:"
    echo "  ✗ CloudWatch PutMetricData permission missing"
    echo ""
    echo "You can still run tests 1-3, 6-12 (non-CloudWatch tests)"
    echo "Tests 4-5 (CloudWatch) will be skipped."
    echo ""
    echo "To run limited tests:"
    echo "  ./scripts/run_manual_tests.sh config/config.yaml \"1 2 3 6 7 8 9 10 11 12\""
    exit 0
fi
