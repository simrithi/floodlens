#!/usr/bin/env bash
# Read-only proof that the deployed AWS services are live. Changes nothing and calls no paid model.
#   bash infra/verify_aws.sh
# Needs AWS credentials for the account and curl. Prints PASS or FAIL per check and exits non-zero if any fail.
set -uo pipefail
export AWS_PAGER="" PYTHONUTF8=1
R=us-east-1
SITE=https://d24wvc44c3vaxz.cloudfront.net
fails=0
pass() { printf 'PASS  %-28s %s\n' "$1" "$2"; }
fail() { printf 'FAIL  %-28s %s\n' "$1" "$2"; fails=$((fails+1)); }
check() { # name, expected, actual, detail
  if [ "$3" = "$2" ]; then pass "$1" "${4:-$3}"; else fail "$1" "expected '$2', got '$3'"; fi
}

ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) || { echo "No AWS credentials"; exit 2; }
echo "Account $ACCOUNT, region $R, $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

# --- delivery: S3 + CloudFront
for p in "" map report/delhi report/bengaluru; do
  check "CloudFront /$p" 200 "$(curl -s -o /dev/null -w '%{http_code}' "$SITE/$p")"
done
for p in findings-delhi.json findings-bengaluru.json 4020141-lth/analysis.json 4020141-full/analysis.json 3827609-lth/analysis.json 9316057-lth/analysis.json; do
  check "site /analysis/$p" 200 "$(curl -s -o /dev/null -w '%{http_code}' "$SITE/analysis/$p")"
done
check "CloudFront distribution" Deployed "$(aws cloudfront get-distribution --id E27HTQ0D9GRDDR --query Distribution.Status --output text)"
for b in floodlens-raw-$ACCOUNT floodlens-outputs-$ACCOUNT floodlensweb-sitebucket397a1860-lklujpasrixv; do
  v=$(aws s3api get-public-access-block --bucket "$b" --query 'PublicAccessBlockConfiguration.[BlockPublicAcls,IgnorePublicAcls,BlockPublicPolicy,RestrictPublicBuckets]' --output text | tr '\t' ',')
  check "S3 public access blocked" "True,True,True,True" "$v" "$b"
done

# --- the models on SageMaker
check "SageMaker endpoint" InService "$(aws sagemaker describe-endpoint --endpoint-name floodlens-analyze --region $R --query EndpointStatus --output text)" "floodlens-analyze (ml.g4dn.xlarge)"

# --- orchestration
check "Step Functions" ACTIVE "$(aws stepfunctions describe-state-machine --state-machine-arn arn:aws:states:$R:$ACCOUNT:stateMachine:floodlens-pipeline --region $R --query status --output text)" "floodlens-pipeline"
check "EventBridge rule" ENABLED "$(aws events describe-rule --name floodlens-frames-uploaded --region $R --query State --output text)" "floodlens-frames-uploaded"
check "EventBridge Scheduler" ENABLED "$(aws scheduler get-schedule --name floodlens-daily-forecast --region $R --query State --output text)" "$(aws scheduler get-schedule --name floodlens-daily-forecast --region $R --query '[ScheduleExpression,ScheduleExpressionTimezone]' --output text | tr '\t' ' ')"

# --- Lambda
for f in start-run get-upload-url get-run-status invoke-frame assemble-results frame-check officer-brief forecast actions; do
  s=$(aws lambda get-function-configuration --function-name floodlens-$f --region $R --query '[State,LastUpdateStatus]' --output text | tr '\t' '/')
  check "Lambda floodlens-$f" "Active/Successful" "$s"
done
for f in frame-check officer-brief actions; do
  u=$(aws lambda get-function-url-config --function-name floodlens-$f --region $R --query AuthType --output text 2>/dev/null)
  check "Function URL $f" NONE "$u" "public, called by the browser"
done

# --- Bedrock (the models are invoked through frame-check and officer-brief; this only checks the policy)
n=$(aws iam get-role-policy --role-name floodlens-lambda-execution --policy-name floodlens-lambda-permissions --query 'PolicyDocument.Statement[?Sid==`BedrockVisionAndText`].Resource[]' --output text | tr '\t' '\n' | grep -c "nova-\(lite\|pro\)")
check "Bedrock access (Nova)" 4 "$n" "Nova Lite and Nova Pro only"

# --- data, messaging, secrets
for t in floodlens-runs FloodLensActions; do
  check "DynamoDB $t" ACTIVE "$(aws dynamodb describe-table --table-name $t --region $R --query Table.TableStatus --output text)"
done
sub=$(aws sns list-subscriptions-by-topic --topic-arn arn:aws:sns:$R:$ACCOUNT:floodlens-alerts --region $R --query 'Subscriptions[0].SubscriptionArn' --output text)
case "$sub" in arn:aws:sns:*) pass "SNS subscription" "confirmed (email)";; *) fail "SNS subscription" "$sub";; esac
check "SSM officer passcode" SecureString "$(MSYS_NO_PATHCONV=1 aws ssm get-parameter --name /floodlens/officer-passcode --region $R --query Parameter.Type --output text)" "value not read"
for r in floodlens-serve floodlens-assemble; do
  c=$(aws ecr describe-images --repository-name $r --region $R --query 'length(imageDetails)' --output text)
  [ "${c:-0}" -gt 0 ] && pass "ECR $r" "$c images" || fail "ECR $r" "no images"
done

# --- monitoring and cost
al=$(aws cloudwatch describe-alarms --region $R --query "length(MetricAlarms[?contains(AlarmName,'lood')])" --output text)
[ "$al" -ge 10 ] && pass "CloudWatch alarms" "$al alarms ($(aws cloudwatch describe-alarms --region $R --state-value ALARM --query "length(MetricAlarms[?contains(AlarmName,'lood')])" --output text) currently in ALARM)" || fail "CloudWatch alarms" "$al"
bad=$(MSYS_NO_PATHCONV=1 aws logs describe-log-groups --log-group-name-prefix /aws/ --region $R --query "length(logGroups[?(contains(logGroupName,'floodlens')) && retentionInDays!=\`14\`])" --output text)
check "Log retention 14 days" 0 "$bad" "every floodlens log group"
b=$(aws budgets describe-budgets --account-id "$ACCOUNT" --query "length(Budgets[?BudgetName=='FloodLens-Monthly'])" --output text)
check "AWS Budget" 1 "$b" "FloodLens-Monthly, US\$25"

echo
if [ "$fails" -eq 0 ]; then echo "All checks passed."; else echo "$fails check(s) failed."; exit 1; fi
