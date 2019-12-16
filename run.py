#!/usr/bin/env python3

import codecs
import glob
import json
import logging
import shutil
import os
import shutil
import subprocess as sp
import sys
import logging
import flywheel
from subprocess import Popen, PIPE, STDOUT
import time
from common import exec_command, build_command_list
import nibabel as nb
import numpy as np


##-------- Standard Flywheel Gear Structure --------##
flywheelv0 = "/flywheel/v0"
environ_json = '/tmp/gear_environ.json'

##--------    Gear Specific files/folders   --------##


def exists(file, log, ext=-1, is_expected=True, quit_on_error=True):
    """
    Generic 'if exists' function that checks for files/folders and takes care of logging in the event of
    nonexistance.

    :param file: the file or folder to check for existence
    :type file: str
    :param log: the python logger being used to output log messages to
    :type log: class:`logging.RootLogger`
    :param ext: the extension that's expected to be on the file
    :type ext: Union[str, int], optional
    :param is_expected: indicate if we expect the file/folder to exist (True), or not (false)
    :type is_expected: bool
    :param quit_on_error: indicate if this file is critical for the performance of the code, and raise exception if
    the conditions set by the previous variables aren't met
    :type quit_on_error: bool
    :return: path_exists, true or false if the path is as expected
    :rtype: bool
    """


    path_exists=os.path.exists(file)

    # If we find the file and are expecting to
    if path_exists and is_expected:
        log.info('located {}'.format(file))

    # If we don't find the file and are expecting to
    elif not path_exists and is_expected:
        # and if that file is critical
        if quit_on_error:
            # Quit the program
            raise Exception('Unable to locate {} '.format(file))

            # Otherwise, we'll manage.  Keep on trucking.
        else:
            log.warning('Unable to locate {} '.format(file))

    # If we don't find the file and we weren't expecting to:
    elif not path_exists and not is_expected:
        # Then we're all good, keep on trucking
        log.info('{} is not present or has been removed successfully'.format(file))

    # If we don't expect the file to be there, but it is...DUN DUN DUNNNN
    elif path_exists and not is_expected:
        # and if that file is critical
        if quit_on_error:
            # Well, you know the drill by now.
            raise Exception('file {} is present when it must be removed'.format(file))
        else:
            log.warning('file {} is present when it should be removed'.format(file))

    # Now we'll check the file extension (if desired)
    if isinstance(ext, str):
        ext_period = ext.count('.')
        file_name = os.path.split(file)[-1]
        div_by_period = file_name.split('.')

        if len(div_by_period) <= ext_period:
            raise Exception('Extension {} too long for file {}'.format(ext,file_name))

        file_ext = div_by_period[-ext_period:]
        file_ext = '.'+'.'.join(file_ext)

        if not file_ext == ext:
            raise Exception('Incorrect file type for input {}, expected {}, got {}'.format(file, ext, file_ext))


    return path_exists


def set_environment(log):

    # Let's ensure that we have our environment .json file and load it up
    exists(environ_json, log)

    # If it exists, read the file in as a python dict with json.load
    with open(environ_json, 'r') as f:
        log.info('Loading gear environment')
        environ = json.load(f)

    # Now set the current environment using the keys.  This will automatically be used with any sp.run() calls,
    # without the need to pass in env=...  Passing env= will unset all these variables, so don't use it if you do it
    # this way.
    for key in environ.keys():
        os.environ[key] = environ[key]

    # Pass back the environ dict in case the run.py program has need of it later on.
    return environ


def make_mat(tx,ty,tz,rx,ry,rz):
    R_x = np.matrix([[1, 0, 0, 0],
                     [0, np.cos(rx), np.sin(rx), 0],
                     [0, -np.sin(rx), np.cos(rx), 0],
                     [0, 0, 0, 1]
                     ])

    R_y = np.matrix([[np.cos(ry), 0, -np.sin(ry), 0],
                     [0, 1, 0, 0],
                     [np.sin(ry), 0, np.cos(ry), 0],
                     [0, 0, 0, 1]
                     ])

    R_z = np.matrix([[np.cos(rz), np.sin(rz), 0, 0],
                     [-np.sin(rz), np.cos(rz), 0, 0],
                     [0, 0, 1, 0],
                     [0, 0, 0, 1]
                     ])

    R = R_x*R_y*R_z

    R[0, -1] = tx
    R[1, -1] = ty
    R[2, -1] = tz

    return(R)

def is4D(image):
    shape = nb.load(image).header.get_data_shape()
    if len(shape) < 4:
        return(False)
    elif shape[3] > 1:
        return(True)
    else:
        return(False)




def check_inputs(context):

    log=logging.getLogger()
    apply_to_files=[]
    index_list=[]

    image1_path = context.get_input_path('image_1')
    image2_path = context.get_input_path('image_2')
    config_path = context.get_input_path('config_file')
    apply_to_a = context.get_input_path('apply_to_a')
    apply_to_b = context.get_input_path('apply_to_b')
    acq_par = context.get_input_path('acquisition_parameters')

    if is4D(image1_path):
        apply_to_files.append(image1_path)
        index_list.append('1')
        log.info('Will run applytopup on {}'.format(image1_path))
    if is4D(image2_path):
        apply_to_files.append(image2_path)
        index_list.append('2')
        log.info('Will run applytopup on {}'.format(image2_path))
    if apply_to_a:
        apply_to_files.append(apply_to_a)
        index_list.append('1')
        log.info('Will run applytopup on {}'.format(apply_to_a))
    if apply_to_b:
        apply_to_files.append(apply_to_b)
        index_list.append('2')
        log.info('Will run applytopup on {}'.format(apply_to_b))

    parameters = open(acq_par,'r')
    log.info(parameters.read())
    parameters.close()

    if config_path:
        log.info('Using config settings in {}'.format(config_path))
        parameters = open(config_path,'r')
        log.info(parameters.read())
        parameters.close()
    else:
        log.info('Using default config values')

    return(apply_to_files,index_list)



def generate_topup_input(context):

    log=logging.getLogger()

    image1_path = context.get_input_path('image_1')
    image2_path = context.get_input_path('image_2')
    work_dir = context.work_dir

    base_out1 = os.path.join(work_dir, 'Image1')
    if is4D(image1_path):
        im_name = os.path.split(image1_path)[-1]
        log.info('Using volume 1 in 4D image {}'.format(im_name))

        cmd = ['fslroi', image1_path, base_out1, '0', '1']
    else:
        cmd = ['fslmaths',image1_path,base_out1]
    exec_command(context, cmd)


    base_out2 = os.path.join(work_dir, 'Image2')
    if is4D(image2_path):
        im_name = os.path.split(image2_path)[-1]
        log.info('Using volume 1 in 4D image {}'.format(im_name))

        cmd = ['fslroi', image2_path, base_out2, '0', '1']
    else:
        cmd = ['fslmaths', image2_path, base_out2]
    exec_command(context, cmd)


    merged = os.path.join(work_dir, 'topup_vols')
    cmd = ['fslmerge', '-t', merged, base_out1, base_out2]
    exec_command(context, cmd)

    return(merged)

def run_topup(context,input):

    output_dir = context.output_dir
    config_path = context.get_input_path('config_file')
    acq_par = context.get_input_path('acquisition_parameters')

    fout = os.path.join(output_dir, 'topup_out_fmap')
    dfout = os.path.join(output_dir,'topup_out_warpfield')
    iout = os.path.join(output_dir, 'topup_out_corrected')
    out = os.path.join(output_dir, 'topup_out')


    if config_path:
        cmd = ['topup', '--imain={}'.format(input), '--datain={}'.format(acq_par), '--out={}'.format(out),
           '--iout={}'.format(iout), '--fout={}'.format(fout), '--config={}'.format(config_path),'--dfout={}'.format(dfout)]

    else:
        cmd = ['topup', '--imain={}'.format(input), '--datain={}'.format(acq_par), '--out={}'.format(out),
               '--iout={}'.format(iout), '--fout={}'.format(fout), '--fwhm=0','--dfout={}'.format(dfout)]
    exec_command(context, cmd)

    return(out)

def apply_warp(context,apply_topup_files,index_list,topup_out):

    motion = np.loadtxt('{}_movpar.txt'.format(topup_out))

    for fl, ix in zip(apply_topup_files, index_list):

        base = os.path.split(fl)[-1]
        warp = topup_out + '_warpfield_{:02d}.nii.gz'.format(int(ix))
        m = motion[int(ix)]
        R = make_mat(m[0], m[1], m[2], m[3], m[4], m[5])
        matout = topup_out + '_temp_mat.txt'
        np.savetxt(matout,R)
        cmd = ['applywarp',
               '--in={}'.format(fl),
               '--ref={}'.format(fl),
               '--warp={}'.format(warp),
               '--premat={}'.format(matout),
               '--out={}'.format(os.path.join(context.output_dir, 'topup_corrected_{}'.format(base)))]

        exec_command(context, cmd)



def apply_topup(context,apply_topup_files,index_list,topup_out):

    acq_par = context.get_input_path('acquisition_parameters')
    for fl, ix in zip(apply_topup_files, index_list):
        base = os.path.split(fl)[-1]
        cmd = ['applytopup',
               '--imain={}'.format(fl),
               '--datain={}'.format(acq_par),
               '--inindex={}'.format(ix),
               '--topup={}'.format(topup_out),
               '--out={}'.format(os.path.join(context.output_dir, 'topup_corrected_{}'.format(base)))]

        exec_command(context, cmd)



def main():

    # shutil.copy('config.json','/flywheel/v0/output/config.json')
    with flywheel.gear_context.GearContext() as gear_context:

        #### Setup logging as per SSE best practices
        fmt = '%(asctime)s %(levelname)8s %(name)-8s - %(message)s'
        logging.basicConfig(level=gear_context.config['gear-log-level'], format=fmt)
        log = logging.getLogger('[flywheel/fwl-topup]')
        log.info('log level is ' + gear_context.config['gear-log-level'])
        gear_context.log_config()  # not configuring the log but logging the config

        # Now let's set up our environment from the .json file stored in the docker image:
        environ = set_environment(log)
        output_dir = gear_context.output_dir
        work_dir = gear_context.work_dir

        work_dir = output_dir
        os.makedirs(work_dir, exist_ok=True)

        log.info('Checking inputs')
        apply_to_files,index_list = check_inputs(gear_context)

        log.info('Generating topup input')
        topup_input = generate_topup_input(gear_context)

        log.info('Running Topup')
        topup_out = run_topup(gear_context, topup_input)


        if not gear_context.config['topup_only']:
            log.info('Applying Topup Correction')
            #apply_topup(gear_context, apply_to_files, index_list, topup_out)
            apply_warp(gear_context, apply_to_files, index_list, topup_out)





if __name__ == "__main__":
    main()