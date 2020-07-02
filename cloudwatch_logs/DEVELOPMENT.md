## Creating a test release

Creating a release to test your changes without making that release public requires changing the `publish.sh` file.
 The value of `BUCKETS` on line 9 should be changed to contain only the name of a private bucket you have write
 permissions to. You should have the AWS cli client installed and configured with the credentials that have access to
 this bucket, then simply run `publish.sh` and use the generated link output by the script.


## Creating a real release

1. Update the version value in the `VERSION` file, merging it to master.

2. If you have access to Scalyr production S3 buckets run `publish.sh`, if not poke the SRE czar to do it for you.
 Take note of the link output at the end of the run of this script.

3. Update the `README.md` file to replace the old "Launch Stack" link with the one output by the script.
 Merge this to master as well.
