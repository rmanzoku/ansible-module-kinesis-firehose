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

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.ec2 import ec2_argument_spec, boto3_conn, get_aws_connection_info


def main():

    argument_spec = ec2_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type='str', default="present", choices=['present', 'absent']),
            name=dict(type='str', required=True),
            stream_type=dict(type='str', require=True, choices=['DirectPut']),
            dest=dict(type='str', require=True, choices=['Elasticsearch']),
            role_arn=dict(type='str', require=True),
            dest_arn=dict(type='str', require=True, aliases=['domain_arn']),
            backup_mode=dict(default="FailedDocumentsOnly", type='str',
                             choices=['FailedDocumentsOnly', 'AllDocuments']),
            es_index_name=dict(type='str', require=True),
            es_type_name=dict(type='str', require=True),
            es_index_rotation_period=dict(default="NoRotation", type='str', require=False,
                                          choices=['NoRotation', 'OneHour', 'OneDay', 'OneWeek', 'OneMonth']),
            es_buffering_second=dict(default=300, type='int', require=False),
            es_buffering_mb=dict(default=5, type='int', require=False),
            es_retry_second=dict(default=300, type='int', require=False),
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
    dest = module.params['dest']
    role_arn = module.params['role_arn']
    dest_arn = module.params['dest_arn']
    backup_mode = module.params['backup_mode']
    es_index_name = module.params['es_index_name']
    es_type_name = module.params['es_type_name']
    es_index_rotation_period = module.params['es_index_rotation_period']
    es_buffering_second = module.params['es_buffering_second']
    es_buffering_mb = module.params['es_buffering_mb']
    es_retry_second = module.params['es_retry_second']
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
    s3_configuration = {
        "RoleARN": role_arn,
        "BucketARN": s3_bucket_arn,
        "Prefix": s3_prefix,
        "CompressionFormat": s3_compression
    }

    if dest == "Elasticsearch":
        elasticsearch_destination_configuration = {
            "RoleARN": role_arn,
            "DomainARN": dest_arn,
            "IndexName": es_index_name,
            "TypeName": es_type_name,
            "IndexRotationPeriod": es_index_rotation_period,
            "BufferingHints": {
                "IntervalInSeconds": es_buffering_second,
                "SizeInMBs": es_buffering_mb
            },
            "RetryOptions": {
                "DurationInSeconds": es_retry_second
            },
            "S3BackupMode": backup_mode,
            "S3Configuration": s3_configuration
        }

        try:
            conn.create_delivery_stream(
                DeliveryStreamName=name,
                DeliveryStreamType=stream_type,
                ElasticsearchDestinationConfiguration=elasticsearch_destination_configuration
            )
            changed = True
        except ClientError as ex:
            if ex.response['Error']['Code'] == "ResourceInUseException":
                pass
            else:
                module.fail_json(msg=ex.response['Error']['Message'])

    module.exit_json(changed=True)


if __name__ == '__main__':
    main()
