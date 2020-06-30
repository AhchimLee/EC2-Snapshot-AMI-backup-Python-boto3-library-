# Automated AMI Backups

import boto3
import collections
import datetime 

ec = boto3.client('ec2', 'ap-northeast-2')

def create_ami():
    reservations = ec.describe_instances(
        Filters=[
			{ 'Name': 'tag:Backup', 'Values': ['Y'] },
            { 'Name': 'instance-state-name', 'Values': ['running'] }
        ]
         ).get(
        'Reservations', []
    )
    
    instances = sum(
        [
            [i for i in r['Instances']]
            for r in reservations
        ], [])

    print("Found %d instances that need backing up" % len(instances))
   
    
    to_tag = collections.defaultdict(list)

    for instance in instances:
        print("Instance name:" + [res['Value'] for res in instance['Tags'] if res['Key'] == 'Name'][0])
        
        #Default retention for 14 days if the tag is not specified
        try:
            retention_days = [
                int(t.get('Value')) for t in instance['Tags']
                if t['Key'] == 'Retention'][0]
        except IndexError:
            retention_days = 14
        except ValueError:
            retention_days = 14
        except Exception as e:    
            retention_days = 14
        
        finally:
            create_time = datetime.datetime.now()
            create_fmt = create_time.strftime('%Y-%m-%d')
    
            try:
                name = [tag['Value'] for tag in instance['Tags'] if tag['Key'] == 'Name'][0] + "-" + create_fmt
                
                AMIid=ec.create_image(
                    InstanceId=instance['InstanceId'], 
                    Name=name, 
                    Description="Lambda created AMI of instance " + instance['InstanceId'],
                    NoReboot=True, 
                    DryRun=False)
                                        
                to_tag[retention_days].append(AMIid['ImageId'])

                print("Retaining AMI %s of instance %s for %d days" % (
                        AMIid['ImageId'],
                        instance['InstanceId'],
                        retention_days
                    )
                )

                delete_date = datetime.date.today() + datetime.timedelta(days=retention_days)
                delete_fmt = delete_date.strftime('%Y-%m-%d')
                
                ec.create_tags(
                    Resources=[AMIid['ImageId']],
                    Tags=[
                            {'Key': 'Name', 'Value': name},
                            {'Key': 'DeleteOn', 'Value': delete_fmt}
                    ]
                )
            
            #If the instance is not in running state        
            except IndexError as e:
                print("Unexpected error, instance "+[res['Value'] for res in instance['Tags'] if res['Key'] == 'Name'][0]+"-"+"\""+instance['InstanceId']+"\""+" might be in the state other then 'running'. So, AMI creation skipped.")

def delete_ami():
    images = ec.describe_images(Owners=['self'])['Images']
    snapshots = ec.describe_snapshots(OwnerIds=['self'])['Snapshots']
    
    timeLimit = datetime.datetime.now() - datetime.timedelta(days=14) 
    imageDeleteFlag = False
    
    for image in images:
        creationDate = datetime.datetime.strptime(image['CreationDate'].split('T')[0], '%Y-%m-%d').date()
        deleteOntag = [tag['Key'] for tag in image.get('Tags', 'N') if tag != 'N' and tag['Key'] == 'DeleteOn']
        
        if deleteOntag and creationDate <= timeLimit.date():
            print("Deregistering image %s" % image['ImageId'])
            amiResponse = ec.deregister_image(
                DryRun=False,
                ImageId=image['ImageId'],
            )
            imageDeleteFlag = True
        else:
            print("Remain image %s" % image['ImageId'])
            imageDeleteFlag = False


        for snapshot in snapshots:
            strdate = snapshot['StartTime'].date()
            
            if snapshot['Description'].find(image['ImageId']) > 0:
                if imageDeleteFlag == True and strdate <= timeLimit.date():
                    snap = ec.delete_snapshot(SnapshotId=snapshot['SnapshotId'])
                    print("Deleting snapshot " + snapshot['SnapshotId'])
                    print("-------------")
                else:
                    print("Remain snapshot " + snapshot['SnapshotId'])
                    print("-------------")
        imageDeleteFlag = False


def lambda_handler(event, context):
    create_ami()
    delete_ami()
    
    return 'successful'