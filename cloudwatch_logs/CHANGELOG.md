## 1.0.9 - July 23, 2020

Bug fixes:
* Fixed issue causing "RequestEntityTooLarge" exceptions when updating the Lambda policy in accounts 
with a large number of log groups. Previously, each log group was given permission to invoke the Lambda. 
Now, all log groups within the AWS account are allowed to invoke the Lambda.
 
Misc:
* Added documentation for the manual test deployment.

## 1.0.8 - July 02, 2020

Features:

* Added new `attributes` log option allowing you to add fixed attributes to all events belonging to a log group.

## 1.0.7 - March 24, 2020

Features:

* Added `prefix_timestamp` log group option which will prefix all log lines with the event timestamp.

## 1.0.6 - January 28, 2020

Features:

* Added `sampling_rules` and `redaction_rules` to the available log group options. Allows sampling and redacting log lines before being sent to Scalyr.
