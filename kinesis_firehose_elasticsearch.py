#!/usr/bin/python
# coding: utf-8

DOCUMENTATION = '''
---
module: kinesis_firehose_elasticsearch
short_description: Manage a Kinesis Firehose for Elasticsearch.
description:
    - Manage a Kinesis Firehose for Elasticsearch service.
options:
  state:
    description: Create or Delete the Kinesis Firehose.
    choices: [ "present", "absent" ]
  name:
    description: The name of the Kinesis Firehose you are managing.
    required: true
author:
    - "Ryo Manzoku (@rmanzoku)"
extends_documentation_fragment: aws
'''

EXAMPLES = '''
'''

try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

try:
    from botocore.exceptions import ClientError, NoCredentialsError
    HAS_BOTOCORE = True
except ImportError:
    HAS_BOTOCORE = False

import copy
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.ec2 import ec2_argument_spec, boto3_conn, get_aws_connection_info


def main():

    argument_spec = ec2_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type='str', default="present", choices=['present', 'absent']),
            name=dict(type='str', required=True),
            stream_type=dict(type='str', require=True, choices=['DirectPut']),
            role_arn=dict(type='str', require=True),
            dest_arn=dict(type='str', require=True, aliases=['domain_arn']),
            backup_mode=dict(default="FailedDocumentsOnly", type='str',
                             choices=['FailedDocumentsOnly', 'AllDocuments']),
            index_name=dict(type='str', require=True),
            type_name=dict(type='str', require=True),
            index_rotation_period=dict(default="NoRotation", type='str', require=False,
                                       choices=['NoRotation', 'OneHour', 'OneDay', 'OneWeek', 'OneMonth']),
            buffering_second=dict(default=300, type='int', require=False),
            buffering_mb=dict(default=5, type='int', require=False),
            retry_second=dict(default=300, type='int', require=False),
            s3_bucket_arn=dict(type='str', require=True),
            s3_prefix=dict(default="", type='str', require=False),
            s3_compression=dict(default="UNCOMPRESSED", type='str', require=False,
                                choices=['UNCOMPRESSED', 'SNAPPY', 'ZIP', 'GZIP']),
        )
    )

    module = AnsibleModule(argument_spec=argument_spec)

    state = module.params['state']
    name = module.params['name']
    stream_type = module.params['stream_type']
    role_arn = module.params['role_arn']
    dest_arn = module.params['dest_arn']
    backup_mode = module.params['backup_mode']
    index_name = module.params['index_name']
    type_name = module.params['type_name']
    index_rotation_period = module.params['index_rotation_period']
    buffering_second = module.params['buffering_second']
    buffering_mb = module.params['buffering_mb']
    retry_second = module.params['retry_second']
    s3_bucket_arn = module.params['s3_bucket_arn']
    s3_prefix = module.params['s3_prefix']
    s3_compression = module.params['s3_compression']

    changed = False

    if not HAS_BOTO3:
        module.fail_json(msg='boto3 required for this module')
    if not HAS_BOTOCORE:
        module.fail_json(msg='botocore required for this module')

    # Connect to AWS
    try:
        region, ec2_url, aws_connect_kwargs = get_aws_connection_info(module, boto3=True)
        conn = boto3_conn(module, conn_type="client", resource="firehose", region=region,
                          **aws_connect_kwargs)
    except NoCredentialsError as ex:
        module.fail_json(msg=ex.message)

    if state == "absent":
        try:
            conn.delete_delivery_stream(
                DeliveryStreamName=name
            )
            changed = True

        except ClientError as ex:
            if ex.response['Error']['Code'] == "ResourceNotFoundException":
                changed = False
            else:
                module.fail_json(msg=ex.response['Error']['Message'])

        module.exit_json(changed=changed)

    # state == present
    desired_s3_config = {
        "RoleARN": role_arn,
        "BucketARN": s3_bucket_arn,
        "Prefix": s3_prefix,
        "CompressionFormat": s3_compression,
        "BufferingHints": {
            "IntervalInSeconds": 300,
            "SizeInMBs": 5
        },
        "CloudWatchLoggingOptions": {
            "Enabled": False
        },
        "EncryptionConfiguration": {
            "NoEncryptionConfig": "NoEncryption"
        },
    }

    desired_config = {
        "RoleARN": role_arn,
        "DomainARN": dest_arn,
        "IndexName": index_name,
        "TypeName": type_name,
        "IndexRotationPeriod": index_rotation_period,
        "BufferingHints": {
            "IntervalInSeconds": buffering_second,
            "SizeInMBs": buffering_mb
        },
        "RetryOptions": {
            "DurationInSeconds": retry_second
        },
        "S3BackupMode": backup_mode,
        "S3Configuration": desired_s3_config
    }

    try:
        current = conn.describe_delivery_stream(
            DeliveryStreamName=name
        )

    except ClientError as ex:
        # Create delivery stream
        if ex.response['Error']['Code'] != "ResourceNotFoundException":
            try:
                conn.create_delivery_stream(
                    DeliveryStreamName=name,
                    DeliveryStreamType=stream_type,
                    ElasticsearchDestinationConfiguration=desired_config
                )
                module.exit_json(changed=True)
            except ClientError as ex2:
                module.fail_json(msg=ex2.response['Error']['Message'])

    # Update
    current_config = current['DeliveryStreamDescription']['Destinations'][0]['ElasticsearchDestinationDescription']

    if current_config['S3BackupMode'] != desired_config['S3BackupMode']:
        module.fail_json(msg="You cannot modify S3BackupMode")

    current_config['S3Update'] = current_config.pop('S3DestinationDescription')
    desired_config['S3Update'] = desired_config.pop('S3Configuration')

    planned_config = copy.deepcopy(current_config)

    for k in desired_config.keys():
            planned_config[k] = desired_config[k]

    if current_config == planned_config:
        changed = False

    else:
        planned_config.pop('S3BackupMode')

        try:
            conn.update_destination(
                DeliveryStreamName=name,
                CurrentDeliveryStreamVersionId=current['DeliveryStreamDescription']['VersionId'],
                DestinationId=current['DeliveryStreamDescription']['Destinations'][0]['DestinationId'],
                ElasticsearchDestinationUpdate=planned_config
            )
            changed = True
        except ClientError as ex:
            module.fail_json(msg=ex.response['Error']['Message'])

    module.exit_json(changed=changed)


if __name__ == '__main__':
    main()
