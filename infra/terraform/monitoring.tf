# ---------------------------------------------------------------------
#  Alarms.
#
#  `alert_email` was declared in variables.tf and nothing read it — the variable
#  promised monitoring that did not exist. These are the alarms it was for.
#
#  Only metrics EC2 publishes on its own are used. Memory and disk need the
#  CloudWatch agent installed on the instance; that is worth doing later, but an
#  alarm that silently never fires is worse than no alarm, so nothing here depends
#  on an agent that is not installed.
#
#  Application-level health is covered separately by qa/health-check.sh, which reads
#  /health and exits 0/1/2 — point a cron job or an uptime checker at it.
# ---------------------------------------------------------------------

resource "aws_sns_topic" "alerts" {
  name = "${local.name}-alerts"
}

# AWS e-mails a confirmation link once. Until someone clicks it the subscription
# stays "pending confirmation" and no alarm reaches anyone — worth checking after
# the first apply.
resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# The instance is gone, wedged, or failed its hypervisor check. Everything else in
# this file is a symptom; this is the outage.
resource "aws_cloudwatch_metric_alarm" "status_check" {
  alarm_name          = "${local.name}-status-check-failed"
  alarm_description   = "EC2 instance or system status check has failed. The site is down."
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  dimensions          = { InstanceId = aws_instance.cloudvote_app.id }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "breaching"
}

# t3.micro is burstable: sustained high CPU means it is about to run out of credits
# and get throttled, which looks like the site going slow for no reason.
resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "${local.name}-cpu-high"
  alarm_description   = "CPU above 80% for 10 minutes. On a burstable instance this ends in throttling."
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  dimensions          = { InstanceId = aws_instance.cloudvote_app.id }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
}

# The credits themselves. This fires before cpu_high turns into throttling, and is
# the one that tells you the instance size is wrong rather than the code.
resource "aws_cloudwatch_metric_alarm" "cpu_credits_low" {
  alarm_name          = "${local.name}-cpu-credits-low"
  alarm_description   = "Burst credit balance is nearly exhausted. Expect throttling; consider a larger instance."
  namespace           = "AWS/EC2"
  metric_name         = "CPUCreditBalance"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  threshold           = 20
  comparison_operator = "LessThanThreshold"
  dimensions          = { InstanceId = aws_instance.cloudvote_app.id }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
}

output "alerts_topic_arn" {
  description = "SNS topic the alarms publish to. Confirm the e-mail subscription before relying on it."
  value       = aws_sns_topic.alerts.arn
}
