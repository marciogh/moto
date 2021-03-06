from __future__ import unicode_literals
# Ensure 'assert_raises' context manager support for Python 2.6
import tests.backport_assert_raises
from nose.tools import assert_raises

import boto
import boto3
from boto.exception import EC2ResponseError, JSONResponseError
import six

import sure  # noqa

from moto import mock_ec2

import logging


@mock_ec2
def test_eip_allocate_classic():
    """Allocate/release Classic EIP"""
    conn = boto.connect_ec2('the_key', 'the_secret')

    with assert_raises(JSONResponseError) as ex:
        standard = conn.allocate_address(dry_run=True)
    ex.exception.reason.should.equal('DryRunOperation')
    ex.exception.status.should.equal(400)
    ex.exception.message.should.equal('An error occurred (DryRunOperation) when calling the AllocateAddress operation: Request would have succeeded, but DryRun flag is set')

    standard = conn.allocate_address()
    standard.should.be.a(boto.ec2.address.Address)
    standard.public_ip.should.be.a(six.text_type)
    standard.instance_id.should.be.none
    standard.domain.should.be.equal("standard")

    with assert_raises(JSONResponseError) as ex:
        standard.release(dry_run=True)
    ex.exception.reason.should.equal('DryRunOperation')
    ex.exception.status.should.equal(400)
    ex.exception.message.should.equal('An error occurred (DryRunOperation) when calling the ReleaseAddress operation: Request would have succeeded, but DryRun flag is set')

    standard.release()
    standard.should_not.be.within(conn.get_all_addresses())


@mock_ec2
def test_eip_allocate_vpc():
    """Allocate/release VPC EIP"""
    conn = boto.connect_ec2('the_key', 'the_secret')

    with assert_raises(JSONResponseError) as ex:
        vpc = conn.allocate_address(domain="vpc", dry_run=True)
    ex.exception.reason.should.equal('DryRunOperation')
    ex.exception.status.should.equal(400)
    ex.exception.message.should.equal('An error occurred (DryRunOperation) when calling the AllocateAddress operation: Request would have succeeded, but DryRun flag is set')

    vpc = conn.allocate_address(domain="vpc")
    vpc.should.be.a(boto.ec2.address.Address)
    vpc.domain.should.be.equal("vpc")
    logging.debug("vpc alloc_id:".format(vpc.allocation_id))
    vpc.release()


@mock_ec2
def test_eip_allocate_invalid_domain():
    """Allocate EIP invalid domain"""
    conn = boto.connect_ec2('the_key', 'the_secret')

    with assert_raises(EC2ResponseError) as cm:
        conn.allocate_address(domain="bogus")
    cm.exception.code.should.equal('InvalidParameterValue')
    cm.exception.status.should.equal(400)
    cm.exception.request_id.should_not.be.none


@mock_ec2
def test_eip_associate_classic():
    """Associate/Disassociate EIP to classic instance"""
    conn = boto.connect_ec2('the_key', 'the_secret')

    reservation = conn.run_instances('ami-1234abcd')
    instance = reservation.instances[0]

    eip = conn.allocate_address()
    eip.instance_id.should.be.none

    with assert_raises(EC2ResponseError) as cm:
        conn.associate_address(public_ip=eip.public_ip)
    cm.exception.code.should.equal('MissingParameter')
    cm.exception.status.should.equal(400)
    cm.exception.request_id.should_not.be.none

    with assert_raises(JSONResponseError) as ex:
        conn.associate_address(instance_id=instance.id, public_ip=eip.public_ip, dry_run=True)
    ex.exception.reason.should.equal('DryRunOperation')
    ex.exception.status.should.equal(400)
    ex.exception.message.should.equal('An error occurred (DryRunOperation) when calling the AssociateAddress operation: Request would have succeeded, but DryRun flag is set')

    conn.associate_address(instance_id=instance.id, public_ip=eip.public_ip)
    eip = conn.get_all_addresses(addresses=[eip.public_ip])[0]  # no .update() on address ):
    eip.instance_id.should.be.equal(instance.id)

    with assert_raises(JSONResponseError) as ex:
        conn.disassociate_address(public_ip=eip.public_ip, dry_run=True)
    ex.exception.reason.should.equal('DryRunOperation')
    ex.exception.status.should.equal(400)
    ex.exception.message.should.equal('An error occurred (DryRunOperation) when calling the DisAssociateAddress operation: Request would have succeeded, but DryRun flag is set')

    conn.disassociate_address(public_ip=eip.public_ip)
    eip = conn.get_all_addresses(addresses=[eip.public_ip])[0]  # no .update() on address ):
    eip.instance_id.should.be.equal(u'')
    eip.release()
    eip.should_not.be.within(conn.get_all_addresses())
    eip = None

    instance.terminate()

@mock_ec2
def test_eip_associate_vpc():
    """Associate/Disassociate EIP to VPC instance"""
    conn = boto.connect_ec2('the_key', 'the_secret')

    reservation = conn.run_instances('ami-1234abcd')
    instance = reservation.instances[0]

    eip = conn.allocate_address(domain='vpc')
    eip.instance_id.should.be.none

    with assert_raises(EC2ResponseError) as cm:
        conn.associate_address(allocation_id=eip.allocation_id)
    cm.exception.code.should.equal('MissingParameter')
    cm.exception.status.should.equal(400)
    cm.exception.request_id.should_not.be.none

    conn.associate_address(instance_id=instance.id, allocation_id=eip.allocation_id)
    eip = conn.get_all_addresses(addresses=[eip.public_ip])[0]  # no .update() on address ):
    eip.instance_id.should.be.equal(instance.id)
    conn.disassociate_address(association_id=eip.association_id)
    eip = conn.get_all_addresses(addresses=[eip.public_ip])[0]  # no .update() on address ):
    eip.instance_id.should.be.equal(u'')
    eip.association_id.should.be.none

    with assert_raises(JSONResponseError) as ex:
        eip.release(dry_run=True)
    ex.exception.reason.should.equal('DryRunOperation')
    ex.exception.status.should.equal(400)
    ex.exception.message.should.equal('An error occurred (DryRunOperation) when calling the ReleaseAddress operation: Request would have succeeded, but DryRun flag is set')

    eip.release()
    eip = None

    instance.terminate()

@mock_ec2
def test_eip_boto3_vpc_association():
    """Associate EIP to VPC instance in a new subnet with boto3"""
    session = boto3.session.Session(region_name='us-west-1')
    service = session.resource('ec2')
    client = session.client('ec2')
    vpc_res = client.create_vpc(CidrBlock='10.0.0.0/24')
    subnet_res = client.create_subnet(
            VpcId=vpc_res['Vpc']['VpcId'], CidrBlock='10.0.0.0/24')
    instance = service.create_instances(**{
        'InstanceType': 't2.micro',
        'ImageId': 'ami-test',
        'MinCount': 1,
        'MaxCount': 1,
        'SubnetId': subnet_res['Subnet']['SubnetId']
    })[0]
    allocation_id = client.allocate_address(Domain='vpc')['AllocationId']
    association_id = client.associate_address(
        InstanceId=instance.id,
        AllocationId=allocation_id,
        AllowReassociation=False)
    instance.load()
    instance.public_ip_address.should_not.be.none
    instance.public_dns_name.should_not.be.none


@mock_ec2
def test_eip_associate_network_interface():
    """Associate/Disassociate EIP to NIC"""
    conn = boto.connect_vpc('the_key', 'the_secret')
    vpc = conn.create_vpc("10.0.0.0/16")
    subnet = conn.create_subnet(vpc.id, "10.0.0.0/18")
    eni = conn.create_network_interface(subnet.id)

    eip = conn.allocate_address(domain='vpc')
    eip.network_interface_id.should.be.none

    with assert_raises(EC2ResponseError) as cm:
        conn.associate_address(network_interface_id=eni.id)
    cm.exception.code.should.equal('MissingParameter')
    cm.exception.status.should.equal(400)
    cm.exception.request_id.should_not.be.none

    conn.associate_address(network_interface_id=eni.id, allocation_id=eip.allocation_id)
    eip = conn.get_all_addresses(addresses=[eip.public_ip])[0]  # no .update() on address ):
    eip.network_interface_id.should.be.equal(eni.id)

    conn.disassociate_address(association_id=eip.association_id)
    eip = conn.get_all_addresses(addresses=[eip.public_ip])[0]  # no .update() on address ):
    eip.network_interface_id.should.be.equal(u'')
    eip.association_id.should.be.none
    eip.release()
    eip = None

@mock_ec2
def test_eip_reassociate():
    """reassociate EIP"""
    conn = boto.connect_ec2('the_key', 'the_secret')

    reservation = conn.run_instances('ami-1234abcd', min_count=2)
    instance1, instance2 = reservation.instances

    eip = conn.allocate_address()
    conn.associate_address(instance_id=instance1.id, public_ip=eip.public_ip)

    # Same ID is idempotent
    conn.associate_address(instance_id=instance1.id, public_ip=eip.public_ip)

    # Different ID detects resource association
    with assert_raises(EC2ResponseError) as cm:
        conn.associate_address(instance_id=instance2.id, public_ip=eip.public_ip, allow_reassociation=False)
    cm.exception.code.should.equal('Resource.AlreadyAssociated')
    cm.exception.status.should.equal(400)
    cm.exception.request_id.should_not.be.none

    conn.associate_address.when.called_with(instance_id=instance2.id, public_ip=eip.public_ip, allow_reassociation=True).should_not.throw(EC2ResponseError)

    eip.release()
    eip = None

    instance1.terminate()
    instance2.terminate()

@mock_ec2
def test_eip_reassociate_nic():
    """reassociate EIP"""
    conn = boto.connect_vpc('the_key', 'the_secret')

    vpc = conn.create_vpc("10.0.0.0/16")
    subnet = conn.create_subnet(vpc.id, "10.0.0.0/18")
    eni1 = conn.create_network_interface(subnet.id)
    eni2 = conn.create_network_interface(subnet.id)

    eip = conn.allocate_address()
    conn.associate_address(network_interface_id=eni1.id, public_ip=eip.public_ip)

    # Same ID is idempotent
    conn.associate_address(network_interface_id=eni1.id, public_ip=eip.public_ip)

    # Different ID detects resource association
    with assert_raises(EC2ResponseError) as cm:
        conn.associate_address(network_interface_id=eni2.id, public_ip=eip.public_ip)
    cm.exception.code.should.equal('Resource.AlreadyAssociated')
    cm.exception.status.should.equal(400)
    cm.exception.request_id.should_not.be.none

    conn.associate_address.when.called_with(network_interface_id=eni2.id, public_ip=eip.public_ip, allow_reassociation=True).should_not.throw(EC2ResponseError)

    eip.release()
    eip = None

@mock_ec2
def test_eip_associate_invalid_args():
    """Associate EIP, invalid args """
    conn = boto.connect_ec2('the_key', 'the_secret')

    reservation = conn.run_instances('ami-1234abcd')
    instance = reservation.instances[0]

    eip = conn.allocate_address()

    with assert_raises(EC2ResponseError) as cm:
        conn.associate_address(instance_id=instance.id)
    cm.exception.code.should.equal('MissingParameter')
    cm.exception.status.should.equal(400)
    cm.exception.request_id.should_not.be.none

    instance.terminate()


@mock_ec2
def test_eip_disassociate_bogus_association():
    """Disassociate bogus EIP"""
    conn = boto.connect_ec2('the_key', 'the_secret')

    with assert_raises(EC2ResponseError) as cm:
        conn.disassociate_address(association_id="bogus")
    cm.exception.code.should.equal('InvalidAssociationID.NotFound')
    cm.exception.status.should.equal(400)
    cm.exception.request_id.should_not.be.none

@mock_ec2
def test_eip_release_bogus_eip():
    """Release bogus EIP"""
    conn = boto.connect_ec2('the_key', 'the_secret')

    with assert_raises(EC2ResponseError) as cm:
        conn.release_address(allocation_id="bogus")
    cm.exception.code.should.equal('InvalidAllocationID.NotFound')
    cm.exception.status.should.equal(400)
    cm.exception.request_id.should_not.be.none


@mock_ec2
def test_eip_disassociate_arg_error():
    """Invalid arguments disassociate address"""
    conn = boto.connect_ec2('the_key', 'the_secret')

    with assert_raises(EC2ResponseError) as cm:
        conn.disassociate_address()
    cm.exception.code.should.equal('MissingParameter')
    cm.exception.status.should.equal(400)
    cm.exception.request_id.should_not.be.none


@mock_ec2
def test_eip_release_arg_error():
    """Invalid arguments release address"""
    conn = boto.connect_ec2('the_key', 'the_secret')

    with assert_raises(EC2ResponseError) as cm:
        conn.release_address()
    cm.exception.code.should.equal('MissingParameter')
    cm.exception.status.should.equal(400)
    cm.exception.request_id.should_not.be.none


@mock_ec2
def test_eip_describe():
    """Listing of allocated Elastic IP Addresses."""
    conn = boto.connect_ec2('the_key', 'the_secret')
    eips = []
    number_of_classic_ips = 2
    number_of_vpc_ips = 2

    #allocate some IPs
    for _ in range(number_of_classic_ips):
        eips.append(conn.allocate_address())
    for _ in range(number_of_vpc_ips):
        eips.append(conn.allocate_address(domain='vpc'))
    len(eips).should.be.equal(number_of_classic_ips + number_of_vpc_ips)

    # Can we find each one individually?
    for eip in eips:
        if eip.allocation_id:
            lookup_addresses = conn.get_all_addresses(allocation_ids=[eip.allocation_id])
        else:
            lookup_addresses = conn.get_all_addresses(addresses=[eip.public_ip])
        len(lookup_addresses).should.be.equal(1)
        lookup_addresses[0].public_ip.should.be.equal(eip.public_ip)

    # Can we find first two when we search for them?
    lookup_addresses = conn.get_all_addresses(addresses=[eips[0].public_ip, eips[1].public_ip])
    len(lookup_addresses).should.be.equal(2)
    lookup_addresses[0].public_ip.should.be.equal(eips[0].public_ip)
    lookup_addresses[1].public_ip.should.be.equal(eips[1].public_ip)

    #Release all IPs
    for eip in eips:
        eip.release()
    len(conn.get_all_addresses()).should.be.equal(0)


@mock_ec2
def test_eip_describe_none():
    """Error when search for bogus IP"""
    conn = boto.connect_ec2('the_key', 'the_secret')

    with assert_raises(EC2ResponseError) as cm:
        conn.get_all_addresses(addresses=["256.256.256.256"])
    cm.exception.code.should.equal('InvalidAddress.NotFound')
    cm.exception.status.should.equal(400)
    cm.exception.request_id.should_not.be.none

