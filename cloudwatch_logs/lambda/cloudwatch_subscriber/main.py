#!/usr/bin/env python3
#
# Copyright 2019 Scalyr Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ------------------------------------------------------------------------
#
# CloudFormation Custom Resource to subscribe CloudWatch logGroups to the
# Scalyr CloudWatch Streamer Lambda Function
#
# author: Tom Gardiner <tom@teppen.io>
import os
import re
import json
import boto3
import signal
import logging
from uuid import UUID, uuid5
from botocore.vendored import requests

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

# Create an AWS CloudWatch Logs client, to interact with the CloudWatch API
CWLOGS = boto3.client('logs')
# Create an AWS Lambda client, to interact with the Lambda API
LAMBDA = boto3.client('lambda')

# Sends a FAILED response to CloudFormation X seconds before the lambda times out
LAMBDA_TIMEOUT = 15

# Used to generate the StatementId in the lambda_add_permission and lambda_remove_permission
# functions. The StatementId is an alphanumeric string and must be identical across Lambda
# invokations as we need to reference it in subsequent calls to the AWS API
UUID_SEED = UUID('e4ce7ea4-1343-427a-9e51-a22aad3dd0a8')

STREAMER_FUNCTION_PERMISSION_NAME = "streamer_function_permission"


def build_resp_headers(json_resp_body):
    """Returns the headers to be used for the CloudFormation response"""
    return {
        # This is required for the pre-signed URL, requests may add a default unsigned
        # content-type
        'content-type': '',
        'content-length': str(len(json_resp_body))
    }


def build_resp_body(event, context, resp_status):
    """Builds the reponse body to send to CloudFormation

    @param event: The AWS event containing the CloudFormation event metadata
    @param content: Provides runtime information regarding the Lambda event

    @type event: dict
    @type context: LambdaContext

    @return: The response body to be sent to CloudFormation using a pre-signed URL
    @rtype: str
    """
    resp_body = {
        'Status': resp_status,
        'Reason': f"See CloudWatch Log Stream: {context.log_stream_name}",
        'PhysicalResourceId': event.get('PhysicalResourceId', context.invoked_function_arn),
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId']
    }
    return json.dumps(resp_body)


def send_resp(event, context, resp_status):
    """Sends a response to CloudFormation using a pre-signed URL in the lambda event

    @param event: The AWS event containing the CloudFormation event metadata
    @param context: Provides runtime information regarding the Lambda event

    @type event: dict
    @type context: LambdaContext

    @return: SUCCESS or FAILED
    @rtype: str
    """
    resp_url = event['ResponseURL']
    json_resp_body = build_resp_body(event, context, resp_status)
    LOGGER.info(f"Built response data: {json_resp_body}")
    try:
        resp = requests.put(resp_url, data=json_resp_body, headers=build_resp_headers(json_resp_body))
        LOGGER.info(f"Status code: {resp.reason}")
    except Exception as e:
        LOGGER.exception(f"Failed sending response: {e}")
        raise


def load_log_group_options(event, resource_properties):
    """Load the logGroupOptions from the CloudFormation event

    @param event: The AWS event containing the CloudFormation event metadata
    @pram resource_properties: The name of the resource properties to load depending on the CF Stack event
        'ResourceProperties': On Create, Update, Delete events
        'OldResourceProperties': Only exists on Update events

    @type event: dict
    @type resource_properties: str

    @return: The logGroupOptions provided by the CloudFormation event
    @rtype: dict
    """
    try:
        log_group_options = json.loads(event[resource_properties]['LogGroupOptions'])
    except:
        LOGGER.exception(f"Error loading {resource_properties} LogGroupOptions")
        raise
    else:
        LOGGER.info(f"Loaded {resource_properties} LogGroupOptions: " + json.dumps(log_group_options))
        return log_group_options


def get_log_groups():
    """Returns a list of all the logGroup names that exist in AWS

    The describe_log_groups command will return max 50 results at a time.
    However if there are more results available it also returns a nextToken to be used
    with the next API call.  We loop until there is no nextToken available which means
    there are no results left.

    @retun: A list of all the logGroups that exist in AWS
    @rtype: list
    """
    log_groups = []
    kwargs = {}
    try:
        while True:
            resp = CWLOGS.describe_log_groups(**kwargs)
            for log_group in resp['logGroups']:
                log_groups.append(log_group['logGroupName'])
            try:
                kwargs['nextToken'] = resp['nextToken']
            except KeyError:
                break
    except:
        LOGGER.exception('Error fetching log groups from AWS')
        raise
    else:
        LOGGER.info('Loaded log groups from AWS: ' + json.dumps(log_groups))
        return log_groups


def match_log_groups(aws_log_groups, log_group_options):
    """Match the array of current logGroups that exist in AWS to the provided
    logGroupOptions.  The first logGroup name and associated options that are matched
    to a logGroup that exists in AWS will be used.  Any following matches are ignored.

    @param aws_log_groups: An array of logGroup names that exist in AWS
    @param log_group_options: The logGroupOptions provided by the CloudFormation event

    @type aws_log_groups: list
    @type log_group_options: dcit

    @return: A dict containing logGroup names that exist in AWS matched to their options
        provided in the CloudFormation event
    @rtype: dict
    """
    matching_log_groups = {}
    for pattern, options in log_group_options.items():
        for aws_log_group in aws_log_groups:
            if not aws_log_group in matching_log_groups:
                if re.fullmatch(pattern, aws_log_group):
                    matching_log_groups[aws_log_group] = options
    LOGGER.info('Matched log groups: ' + json.dumps(matching_log_groups))
    return matching_log_groups


def diff_log_groups(log_group_options, old_log_group_options):
    """Upon a CloudFormation stack Create or Update event, logGroupOptions is passed in the
    event parameter to Lambda.  Upon a CloudFormation Update event the old logGroupOptions is also
    provided. These two dicts are compared to return three sets of logGroup names that were added,
    updated or deleted.

    @param log_group_options: The logGroupOptions provided by the CloudFormation event
    @param old_log_group_options: The previous logGroupOptions that have been replaced (CF Update event)

    @type log_group_options: dict
    @type old_log_group_options: dict

    @return: Three sets of logGroup names that were added, updated or deleted from the
        old logGroupOptions dict
    @rtype: (set, set, set)
    """
    log_group_names = set(log_group_options)
    old_log_group_names = set(old_log_group_options)
    added = log_group_names.difference(old_log_group_names)
    deleted = old_log_group_names.difference(log_group_names)
    intersecting = log_group_names.intersection(old_log_group_names)
    updated = []
    for log_group in intersecting:
        if not log_group_options[log_group] == old_log_group_options[log_group]:
            updated.append(log_group)
    return added, set(updated), deleted


def lambda_add_permission(destination_arn, account_id, region):
    """Adds a lambda:InvokeFunction permission statement to the Streamer Lambda function
    which allows every CloudWatch logGroup to deliver logEvents

    @param destination_arn: The ARN of the Lambda function to subscribe the logGroup to
    @param account_id: The Account Id of the AWS account, from the CloudFormation Event
    @param region: The AWS region, from the CloudFormation Event

    @type destination_arn: str
    @type account_id: str
    @type region: str
    """
    try:
        LAMBDA.add_permission(
            FunctionName=destination_arn,
            # Uses the seed to generate a reproducible alphanumeric string
            StatementId=uuid5(UUID_SEED, STREAMER_FUNCTION_PERMISSION_NAME).hex,
            Action='lambda:InvokeFunction',
            Principal=f"logs.{region}.amazonaws.com",
            SourceArn=f"arn:aws:logs:{region}:{account_id}:*",
            SourceAccount=account_id
        )
    except LAMBDA.exceptions.ResourceConflictException as e:
        # The statement id provided already exists, we must have added the permission in a previous run
        LOGGER.info(f"Warning, lambda permission already exists. No action taken: {e}")
    except:
        LOGGER.exception(f"Error adding lambda permission: {STREAMER_FUNCTION_PERMISSION_NAME}")
        raise
    else:
        LOGGER.info(f"Added lambda permission: {STREAMER_FUNCTION_PERMISSION_NAME}")


def lambda_remove_permission(destination_arn):
    """Removes the lambda:InvokeFunction permission statement from the Streamer Lambda
    function, so any of the log groups can invoke it.

    @param destination_arn: The ARN of the Lambda function to subscribe the logGroup to

    @type destination_arn: str
    """
    try:
        LAMBDA.remove_permission(
            FunctionName=destination_arn,
            # Uses the seed to generate a reproducible alphanumeric string
            StatementId=uuid5(UUID_SEED, STREAMER_FUNCTION_PERMISSION_NAME).hex
        )
    except LAMBDA.exceptions.ResourceNotFoundException as e:
        LOGGER.info(f"Warning, lambda permission doesn't exist. No action taken: {e}")
    except:
        LOGGER.exception(f"Error removing lambda permission: {STREAMER_FUNCTION_PERMISSION_NAME}")
        raise
    else:
        LOGGER.info(f"Removed lambda permission: {STREAMER_FUNCTION_PERMISSION_NAME}")


def put_subscription_filter(log_group_name, options, destination_arn):
    """Creates or updates a CloudWatch Logs Subscription Filter to deliver new log events to
    our lambda function which are then forwarded to Scalyr in near real-time.


    @param log_group_name: The name of the logGroup in AWS
    @param options: A dict containing associated logGroupOptions such as the name and pattern
        of the filter
    @param destination_arn: The ARN of the Lambda function to subcribe the logGroup to

    @type log_group_name: str
    @type options: dict
    @type destination_arn: str
    """
    try:
        CWLOGS.put_subscription_filter(
            filterPattern=options.get('filterPattern', ''),
            filterName=options.get('filterName', 'cloudWatchLogs'),
            logGroupName=log_group_name,
            destinationArn=destination_arn
        )
    except:
        LOGGER.exception(f"Error subscribing: {log_group_name}")
        raise
    else:
        LOGGER.info(f"Subscribed: {log_group_name}")


def delete_subscription_filter(log_group_name, options):
    """Delete a CloudWatch Logs Subscription Filter to stop the delivery of log events to our
    lambda function

    @param log_group_name: The name of the logGroup in AWS
    @param options: A dict containing associated logGroupOptions such as the name and pattern
        of the filter

    @type log_group_name: str
    @type options: dict
    """
    try:
        CWLOGS.delete_subscription_filter(
            filterName=options.get('filterName', 'cloudWatchLogs'),
            logGroupName=log_group_name
        )
    except CWLOGS.exceptions.ResourceNotFoundException as e:
        LOGGER.info(f"Warning, logGroup subscription doesn't exist. No action taken: {e}")
    except:
        LOGGER.exception(f"Error unsubscribing: {log_group_name}")
        raise
    else:
        LOGGER.info(f"Unsubscribed: {log_group_name}")


def process_cf_event(event):
    """Processes a CloudFormation Stack event (Create, Update or Delete)

    Updates the subscriptions on the logGroups based on the new desired state recorded in the
    CloudFormation Stack event. If this is a Create event, then a subscription is created for
    all logGroups matching the logGroupOptions. If it is a Delete event, all existing subscription
    filters are removed. If this is an Update, subscriptions are either added or removed based on
    the new state.

    @param event: The AWS event containing the CloudFormation event metadata
    @type event: dict
    """

    auto_subscribe_log_groups = event['ResourceProperties']['AutoSubscribeLogGroups']
    if auto_subscribe_log_groups == 'true':

        destination_arn = event['ResourceProperties']['DestinationArn']
        account_id = event['ResourceProperties']['AccountId']
        region = event['ResourceProperties']['Region']

        aws_log_groups = get_log_groups()
        log_group_options = load_log_group_options(event, 'ResourceProperties')
        matched_log_group_options = match_log_groups(aws_log_groups, log_group_options)

        if event['RequestType'] == 'Create':
            lambda_add_permission(destination_arn, account_id, region)

            for log_group_name, options in matched_log_group_options.items():
                put_subscription_filter(log_group_name, options, destination_arn)
        elif event['RequestType'] == 'Update':
            lambda_add_permission(destination_arn, account_id, region)

            old_log_group_options = load_log_group_options(event, 'OldResourceProperties')
            old_matched_log_group_options = match_log_groups(aws_log_groups, old_log_group_options)
            added, updated, deleted = diff_log_groups(matched_log_group_options, old_matched_log_group_options)
            if event['OldResourceProperties']['AutoSubscribeLogGroups'] == 'false':
                # We don't know the current state of the subscription filters as we weren't in charge
                for log_group_name, options in matched_log_group_options.items():
                    # So create/update subscription filters for all the logGroups that matched
                    put_subscription_filter(log_group_name, options, destination_arn)
            else:
                # We were in charge previously
                for log_group_name, options in matched_log_group_options.items():
                    # So only create/update subscription filters for added or updated logGroups
                    if log_group_name in added or log_group_name in updated:
                        put_subscription_filter(log_group_name, options, destination_arn)
            for log_group_name, options in old_matched_log_group_options.items():
                # Attempt to delete subcription filters for logGroups that are no longer defined
                if log_group_name in deleted:
                    delete_subscription_filter(log_group_name, options)
        elif event['RequestType'] == 'Delete':
            lambda_remove_permission(destination_arn)
            for log_group_name, options in matched_log_group_options.items():
                delete_subscription_filter(log_group_name, options)

def process_create_log_group_event(event):
    """Processes a CloudWatch CreateLogGroup event

    Subscribes the new log group.

    @param event: The AWS event containing the CloudWatch event metadata
    @type event: dict
    """
    if os.environ['AUTO_SUBSCRIBE_LOG_GROUPS'] == 'true':
        log_group_name = event["detail"]["requestParameters"]["logGroupName"]
        try:
            log_group_options = json.loads(os.environ['LOG_GROUP_OPTIONS'])
        except:
            LOGGER.exception(f"Error loading LogGroupOptions")
            raise
        else:
            LOGGER.info(f"Loaded LogGroupOptions: " + json.dumps(log_group_options))

        matched_group_options = match_log_groups([log_group_name], log_group_options)
        for log_group_name, options in matched_group_options.items():
            put_subscription_filter(log_group_name, options, os.environ['DESTINATION_ARN'])


def lambda_handler(event, context):
    """Invoked by AWS to process the event and associated context
    https://docs.aws.amazon.com/lambda/latest/dg/python-programming-model-handler-types.html

    1.) Registers a timeout handler for LAMBDA_TIMEOUT seconds before the Lambda times-out
    2.) Wraps the processing of the CloudFormation event to catch any unexpected exceptions

    The above ensures that a response is always sent to Cloudformation to avoid a stack
    being stuck waiting for a response from the Custom Resource

    @param event: The AWS event containing the CloudFormation event metadata
    @param context: Provides runtime information regarding the Lambda event

    @type event: dict
    @type context: LambdaContext
    """
    def timeout_handler(sig_num, frame):
        LOGGER.exception('Lambda timed out before completion')
        send_resp(event, context, "FAILED")
    signal.signal(signal.SIGALRM, timeout_handler)

    LOGGER.info('Recieved CF event: ' + json.dumps(event))
    signal.alarm(int(context.get_remaining_time_in_millis() / 1000) - LAMBDA_TIMEOUT)

    send_response = False
    try:
        if "StackId" in event and "RequestType" in event and "ResourceType" in event:
            send_response = True
            process_cf_event(event)
        else:
            process_create_log_group_event(event)
    except:
        if send_response:
            send_resp(event, context, "FAILED")
    else:
        if send_response:
            send_resp(event, context, "SUCCESS")
            signal.alarm(0)
