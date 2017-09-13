#!/usr/bin/python
# coding: utf-8

DOCUMENTATION = '''
---
module: kinesis_firehose_s3
short_description: Manage a Kinesis Firehose for S3.
description:
    - Manage a Kinesis Firehose for S3 service.
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
            state=dict
            (require=False, type='str', default="present",
             choices=['present', 'absent']),

            name=dict
            (require=True, type='str'),

            stream_type=dict
            (require=True, type='str',
             choices=['DirectPut', 'KinesisStreamAsSource']),

            role_arn=dict
            (require=True, type='str'),

            dest_arn=dict
            (require=True, type='str'),

            prefix=dict
            (require=False, type='str', default=""),

            compression=dict
            (require=False, type='str', default="UNCOMPRESSED",
             choices=['UNCOMPRESSED', 'SNAPPY', 'ZIP', 'GZIP']),

            buffering_second=dict
            (require=False, type='int', default=300),

            buffering_mb=dict
            (require=False, type='int', default=5),

        )
    )

    module = AnsibleModule(argument_spec=argument_spec)

    state = module.params['state']
    name = module.params['name']
    stream_type = module.params['stream_type']
    role_arn = module.params['role_arn']
    dest_arn = module.params['dest_arn']
    prefix = module.params['prefix']
    compression = module.params['compression']
    buffering_second = module.params['buffering_second']
    buffering_mb = module.params['buffering_mb']

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

    desired_config = {
        "RoleARN": role_arn,
        "BucketARN": dest_arn,
        "Prefix": prefix,
        "CompressionFormat": compression,
        "BufferingHints": {
            "IntervalInSeconds": buffering_second,
            "SizeInMBs": buffering_mb
        },
        "S3BackupMode": "Disabled",
    }

    try:
        current = conn.describe_delivery_stream(
            DeliveryStreamName=name
        )

    except ClientError as ex:
        # Create delivery stream
        if ex.response['Error']['Code'] == "ResourceNotFoundException":
            try:
                conn.create_delivery_stream(
                    DeliveryStreamName=name,
                    DeliveryStreamType=stream_type,
                    ExtendedS3DestinationConfiguration=desired_config
                )
                module.exit_json(changed=True)
            except ClientError as ex2:
                module.fail_json(msg=ex2.response['Error']['Message'])

    # Update
    current_config = current['DeliveryStreamDescription']['Destinations'][0]['ExtendedS3DestinationDescription']

    planned_config = copy.deepcopy(current_config)
    planned_config['S3BackupUpdate'] = planned_config.pop('S3BackupDescription')

    for k in desired_config.keys():
            planned_config[k] = desired_config[k]

    if current_config == planned_config:
        changed = False

    else:
        # planned_config.pop('S3BackupMode')

        try:
            conn.update_destination(
                DeliveryStreamName=name,
                CurrentDeliveryStreamVersionId=current['DeliveryStreamDescription']['VersionId'],
                DestinationId=current['DeliveryStreamDescription']['Destinations'][0]['DestinationId'],
                ExtendedS3DestinationUpdate=planned_config
            )
            changed = True
        except ClientError as ex:
            module.fail_json(msg=ex.response['Error']['Message'])

    module.exit_json(changed=changed)


if __name__ == '__main__':
    main()
