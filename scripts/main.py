# Main script for running gRPC HotelReservation in tandem with the Intel IPU emulator

import sys
import os
import argparse
import logging
import subprocess

import utils
import metadata


logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger('grpc-hotel-ipu')


def setup_docker_swarm(args):
    advertise_addr = utils.parse_ifconfig(logger)
    docker_swarm_init_str = 'sudo docker swarm init ' + \
                            '--advertise-addr {0}'
    docker_swarm_init_cmd = docker_swarm_init_str.format(advertise_addr)
    docker_service_create_str = 'sudo docker service create ' + \
                                '--name registry ' + \
                                '--publish published={0},target={1} registry:{2}'
    docker_service_create_cmd = docker_service_create_str.format(args.published,
                                                                 args.target,
                                                                 args.registry)
    logger.info('----------------')
    logger.info('Setting up docker swarm...')
    logger.info('advertise-addr: ' + advertise_addr)
    logger.info('Initializing docker swarm...')
    subprocess.Popen(docker_swarm_init_cmd.split()).wait()
    logger.info('Starting local registry on this node...')
    logger.info('published: ' + str(args.published))
    logger.info('target: ' + str(args.target))
    logger.info('registry: ' + str(args.registry))
    subprocess.Popen(docker_service_create_cmd.split()).wait()
    logger.info('Set up docker swarm successfully.')
    logger.info('----------------')


def leave_docker_swarm(is_manager):
    docker_swarm_leave_cmd = 'sudo docker swarm leave --force'
    logger.info('----------------')
    logger.info('Leaving docker swarm...')
    if is_manager:
        logger.info('I am a manager! Waiting for all non-manager nodes to leave...')
        # TODO: Make sure all non-manager nodes have left swarm first
    subprocess.Popen(docker_swarm_leave_cmd.split()).wait()
    logger.info('Left swarm successfully.')
    logger.info('----------------')


def setup_application(application_name, replace_zip, node_ssh_list):
    application_name_upper = application_name.upper()
    if application_name_upper not in metadata.application_info:
        ValueError('specified application does not exist in metadata.appication_info')
    application_info = metadata.application_info[application_name_upper]

    curr_dir = os.getcwd()
    node_ssh_list_path = curr_dir + '/../node-ssh-lists/' + node_ssh_list
    if not os.path.isfile(node_ssh_list_path):
        ValueError('specified ssh command file does not exist grpc-hotel-ipu/ssh-node-lists')
    node_ssh_lines = [line.strip() for line in open(node_ssh_list_path).readlines()]

    # Zip grpc-hotel-ipu/datacenter-soc into grpc-hotel-ipu/zipped-applications
    application_dir_path = application_info['dir_path']
    application_zip_path = '../zipped-applications/' + application_name + '.zip'
    application_folder_paths = application_info['zip_paths']
    zip_cmd_arg1 = ''
    for zip_path in application_folder_paths:
        zip_cmd_arg1 += (' ' + zip_path)
    zip_str = 'zip -r {0} {1}'
    #zip_cmd = zip_str.format(application_zip_path,
    #                         '../datacenter-soc') # TODO: need to change this if ever using different versions on datacenter-soc for different projects
    zip_cmd = zip_str.format(application_zip_path,
                             zip_cmd_arg1)
    logger.info('----------------')
    logger.info('Setting up ' + application_name_upper + '...')
    if os.path.isfile(application_zip_path) and not replace_zip:
        logger.info(application_zip_path + ' already exists and replace-zip not specified, skipping zip step')
    else:
        logger.info('zipping ' + application_zip_path)
        subprocess.Popen(zip_cmd.split()).wait()

    print(zip_cmd)

    # For each node in node_ssh_list, copy application zip and unzip
    scp_str = 'scp {0} {1}@{2}:~/{3}'
    ssh_str = 'ssh {0}@{1}'
    unzip_str = 'yes | unzip ~/{0}'
    cp_str = 'cp -R {0} {1}'
    uid = os.getlogin()
    zip_file_name = utils.extract_path_end(application_zip_path)
    logger.info('copying, unzipping, and organizing ' + zip_file_name + ' for specified nodes')
    for ssh_line in node_ssh_lines:
        addr_only = utils.extract_ssh_addr(ssh_line)
        scp_cmd = scp_str.format(application_zip_path,
                                 uid,
                                 addr_only,
                                 zip_file_name)
        ssh_cmd = ssh_str.format(uid,
                                 addr_only)
        unzip_cmd = unzip_str.format(zip_file_name)
        cp_cmds = []
        for zip_path in application_folder_paths:
            zip_path_end = utils.extract_path_end(zip_path)
            zip_path_dest = '~/' + zip_path_end
            zip_path_src = '~/datacenter-soc/' + zip_path
            cp_cmd = cp_str.format(zip_path_src,
                                   zip_path_dest)
            cp_cmds.append(cp_cmd)
        subprocess.Popen(scp_cmd.split()).wait()
        subprocess.Popen(ssh_cmd.split() + [unzip_cmd]).wait()
        for cmd in cp_cmds:
            subprocess.Popen(ssh_cmd.split() + [cmd]).wait()


def get_args():
    parser = argparse.ArgumentParser(description=__doc__)

    # Setting up docker swarm
    parser.add_argument('--setup-docker-swarm',
                        dest='setup_docker_swarm',
                        action='store_true',
                        help='specify arg to set up docker swarm')
    parser.add_argument('--published',
                        dest='published',
                        type=int,
                        help='specify the published value for creating docker registry service')
    parser.add_argument('--target',
                        dest='target',
                        type=int,
                        help='specify the target value for creating docker registry service')
    parser.add_argument('--registry',
                        dest='registry',
                        type=int,
                        help='specify the registry value for creating docker registry service')

    # Leaving docker swarm
    parser.add_argument('--leave-docker-swarm',
                        dest='leave_docker_swarm',
                        action='store_true',
                        help='specify arg to leave docker swarm')
    parser.add_argument('--is-manager',
                        dest='is_manager',
                        action='store_true',
                        help='specify arg if current docker node is a manager')

    # Setting up DeathStarBench applications on CloudLab nodes
    parser.add_argument('--setup-application',
                        dest='setup_application',
                        action='store_true',
                        help='specify arg to setup specified application')
    parser.add_argument('--application-name',
                        dest='application_name',
                        type=str,
                        help='provide the name of the application')
    parser.add_argument('--replace-zip',
                        dest='replace_zip',
                        action='store_true',
                        help='replace if .zip already exists in grpc-hotel-ipu/zipped-applications')
    parser.add_argument('--node-ssh-list',
                        dest='node_ssh_list',
                        type=str,
                        help='provide name of file within grpc-hotel-ipu/node-ssh-lists/ containing CloudLab ssh commands')

    return parser.parse_args()


if __name__ == '__main__':
    args = get_args()

    if args.setup_docker_swarm:
        if args.published is None:
            raise ValueError('published value should be specified for creating docker registry service')
        if args.target is None:
            raise ValueError('target value should be specified for creating docker registry service')
        if args.registry is None:
            raise ValueError('registry value should be specified for creating docker registry service')
        setup_docker_swarm(args)
    if args.setup_application:
        if args.application_name is None:
            raise ValueError('application name must be provided for application setup')
        if args.node_ssh_list is None:
            raise ValueError('must provide file containing CloudLab ssh commands for application setup')
        setup_application(args.application_name, args.replace_zip, args.node_ssh_list)

    if args.leave_docker_swarm:
        leave_docker_swarm(args.is_manager)
