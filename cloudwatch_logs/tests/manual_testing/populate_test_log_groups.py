#!/usr/bin/env python
# Copyright 2014-2020 Scalyr Inc.
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
#
# ==================================================================
# This is a script to populate log groups with log streams. Used for testing purposes.
# You need to be logged in in the aws cli.

import time
import argparse

import boto3

CWLOGS = boto3.client('logs')


parser = argparse.ArgumentParser()

parser.add_argument(
    "groups_number",
    type=int,
    help="The number of the group logs to create."
)

parser.add_argument(
    "group_name_prefix",
    help="prefix for the log group names."
)

parser.add_argument(
    "--delete",
    action="store_true",
    required=False,
    help="Delete previously created log group instead of creation."
)

args = parser.parse_args()

if args.delete:
    for i in range(args.groups_number):
        group_name = "{}_{}".format(args.group_name_prefix, i)
        print("Delete log group: '{}'".format(group_name))
        CWLOGS.delete_log_group(
            logGroupName=group_name
        )
else:
    for i in range(args.groups_number):
        group_name = "{}_{}".format(args.group_name_prefix, i)
        print("Create log group: '{}'".format(group_name))
        CWLOGS.create_log_group(
            logGroupName=group_name
        )

        log_group_stream_name = '{}_stream'.format(group_name)
        print("Create log stream '{}' in the log group {}.".format(log_group_stream_name, group_name))
        CWLOGS.create_log_stream(
            logGroupName=group_name,
            logStreamName= log_group_stream_name
        )

