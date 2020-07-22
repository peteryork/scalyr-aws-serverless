This is a short instruction how to 

NOTE: some of steps below assume that you have `aws cli` installed and logged in. 

* create one or more S3 buckets.

* Put source code for lambda functions and template file for the CloudFormation stack by running script `publish.sh`
and passing previously created bucket names separated by commas

    ``` ./publish.sh --buckets <bucket_name1,bucket_name2> ```

* Populate test log groups by running python script `populate_test_log_groups.py` with some number name prefix for your log groups.

    ```python tests/manual_testing/populate_test_log_groups.py 300 /aws/lambda/test_log_group```
    
    This will create 300 log groups named test_log_group_1, test_log_group_2, ... test_log_group_300


* Form a new Cloudformation stack creation link. This link contains query parameter named 'templateURL',
 place link to the template `.yml` file from some of your buckets. 
 
    ```https://console.aws.amazon.com/cloudformation/home?#stacks/create/review?stackName=ScalyrCloudWatchLogsImporter&templateURL=<TEMPLATE FILE_URL>``` 

* Open AWS Cloudformation stack creation page by opening this link.

    * set `AutoSubscribeLogGroups` parameter to true to subscribe automatically to the log groups.
    * provide json string with the log group options to the `LogGroupOptions` parameter. 
    For example to subscribe to all log groups from the previous step the json may look like this:
    
        ```{"/aws/lambda/test_log_group_*": {}}```
    * Do not forget to provide Scalyr API write key.
    * Create stack.
    

* Now you should be able to write events to log groups and looks how everything works.

 

 