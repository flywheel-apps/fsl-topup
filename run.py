#!/usr/bin/env python3


import json
import os
import logging
import flywheel
from common import exec_command, build_command_list
import nibabel as nb
import numpy as np
import mri_qa
import shutil

##-------- Standard Flywheel Gear Structure --------##
flywheelv0 = "/flywheel/v0"
environ_json = '/tmp/gear_environ.json'


##--------    Gear Specific files/folders   --------##


def exists(file, log, ext=-1, is_expected=True, quit_on_error=True):
    """
    Generic 'if exists' function that checks for files/folders and takes care of logging in the event of
    Args:
        file (str): the file or folder to check for existence
        log (class:`logging.Logger`): the python logger being used to output log messages to
        ext (Union[str, int], optional): the extension that's expected to be on the file
        is_expected (bool): indicate if we expect the file/folder to exist (True), or not (false)
        quit_on_error (bool): indicate if this file is critical for the performance of the code, and raise exception if
    the conditions set by the previous variables aren't met

    Returns:
        path_exists (bool): true or false if the path is as expected

    """


    path_exists = os.path.exists(file)

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
            raise Exception('Extension {} too long for file {}'.format(ext, file_name))

        file_ext = div_by_period[-ext_period:]
        file_ext = '.' + '.'.join(file_ext)

        if not file_ext == ext:
            raise Exception('Incorrect file type for input {}, expected {}, got {}'.format(file, ext, file_ext))

    return path_exists


def set_environment(log):
    """
    Sets up the docker environment saved in a environment.json file
    Args:
        log (class:`logging.Logger`):

    Returns:
        environ (json): the environment variables in json format
    """

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



def check_inputs(context):
    """
    Checks the inputs of the gear and determines TOPUP run settings, and generates a list of files to apply TOPUP to
    (if indicated by the user)
    Args:
        context (class: `flywheel.gear_context.GearContext`): flywheel gear context

    Returns:
        apply_to_files (list): a list of files to apply the TOPUP correction to after calculating the TOPUP fieldmaps
        index_list (list): the row index in the acquisition_parameters file associated with each file in apply_to_files
    """



    log = logging.getLogger('[flywheel/fsl-topup/check_inputs]')
    apply_to_files = []
    index_list = []

    image1_path = context.get_input_path('image_1')
    image2_path = context.get_input_path('image_2')
    config_path = context.get_input_path('config_file')
    apply_to_a = context.get_input_path('apply_to_1')
    apply_to_b = context.get_input_path('apply_to_2')
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

    parameters = open(acq_par, 'r')
    log.info(parameters.read())
    parameters.close()

    if config_path:
        log.info('Using config settings in {}'.format(config_path))
    else:
        log.info('Using default config values')

    return (apply_to_files, index_list)


def generate_topup_input(context):
    """
    Takes gear input files and generates a merged input file for TOPUP.
    Args:
        context (class: `flywheel.gear_context.GearContext`): flywheel gear context

    Returns:
        merged (string): the path to the merged file for use in TOPUP

    """


    log = logging.getLogger('[flywheel/fsl-topup/generate_topup_input]')

    image1_path = context.get_input_path('image_1')
    image2_path = context.get_input_path('image_2')
    work_dir = context.work_dir

    base_out1 = os.path.join(work_dir, 'Image1')
    if is4D(image1_path):
        im_name = os.path.split(image1_path)[-1]
        log.info('Using volume 1 in 4D image {}'.format(im_name))

        cmd = ['fslroi', image1_path, base_out1, '0', '1']
    else:
        cmd = ['fslmaths', image1_path, base_out1]
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

    return (merged)


def run_topup(context, input):
    """
    Runs topup on a given input image.  Requires acquisition parameters and input options from the gear context.
    Args:
        context (class: `flywheel.gear_context.GearContext`): flywheel gear context
        input (string): the path to the input file for topup's 'imain' input option

    Returns:
        out (string): the topup root path

    """


    log = logging.getLogger('[flywheel/fsl-topup/run_topup]')

    output_dir = context.output_dir
    config_path = context.get_input_path('config_file')

    if not config_path:
        config_path = '/flywheel/v0/b02b0.cnf'

    acq_par = context.get_input_path('acquisition_parameters')

    fout = os.path.join(output_dir, 'topup_fmap')
    iout = os.path.join(output_dir, 'topup_input_corrected')
    out = os.path.join(output_dir, 'topup')

    logout = os.path.join(output_dir, 'topup_log.txt')

    dfout = context.config['displacement_field']
    jacout = context.config['jacobian_determinants']
    rbmout = context.config['rigid_body_matrix']
    verbose = context.config['verbose']
    debug = context.config['topup_debug_level']
    # lout = context.config['mystery_output']

    argument_dict = {'imain': input, 'datain': acq_par, 'out': out, 'fout': fout,
                     'iout': iout, 'logout': logout, 'config': config_path}

    if dfout:
        argument_dict['dfout'] = out + '_dfield'
    if jacout:
        argument_dict['jacout'] = out + '_jacdet'
    if rbmout:
        argument_dict['rbmout'] = out + '_rbmat'
    if verbose:
        argument_dict['verbose'] = True
    if debug:
        argument_dict['debug'] = debug

    log.info('Using config settings:\n\n{}\n\n'.format(open(config_path, 'r').read()))

    command = build_command_list(['topup'], argument_dict)
    exec_command(context, command)

    return (out)


def apply_topup(context, apply_topup_files, index_list, topup_out):
    """
    This function applies a calculated topup correction to a list of files.
    Args:
        context (class: `flywheel.gear_context.GearContext`): flywheel gear context
        apply_topup_files (list): A list of files to apply topup correction to
        index_list (list): A list that corresponds 1:1 with apply_topup_files, this indicates which row to use from the
        "acquisition_parameters" text file for the associated file.  This essentially tells topup what PE direction each
        image is.
        topup_out (string): the base directory/filename for the topup analysis that was run previously.

    Returns:
        output_files (list): a list of topup corrected files

    """
    # applytopup - in = topdn - -topup = mytu - -inindex = 1 - -method = jac - -interp = spline - -out = hifi

    acq_par = context.get_input_path('acquisition_parameters')
    output_files = []
    for fl, ix in zip(apply_topup_files, index_list):
        base = os.path.split(fl)[-1]
        output_file = os.path.join(context.output_dir, 'topup_corrected_{}'.format(base))
        output_files.append(output_file)
        cmd = ['applytopup',
               '--imain={}'.format(fl),
               '--datain={}'.format(acq_par),
               '--inindex={}'.format(ix),
               '--topup={}'.format(topup_out),
               '--method=jac',
               '--interp=spline',
               '--out={}'.format(output_file)]

        exec_command(context, cmd)

    return (output_files)


def main():
    """
    This script runs TOPUP on two images provided in the gear. It will apply the calculated topup correction to the
    inputs, as well as two additional files you provide, "apply_to_1" and "apply_to_2".  The image "apply_to_1" must
    have the same PE direction as "Image_1", and "apply_to_2" must have the same PE direction as "Image_2".

    Returns: None

    """

    # shutil.copy('config.json','/flywheel/v0/output/config.json')
    with flywheel.gear_context.GearContext() as gear_context:

        #### Setup logging as per SSE best practices
        try:
            fmt = '%(asctime)s %(levelname)8s %(name)-8s - %(message)s'
            logging.basicConfig(level=gear_context.config['gear-log-level'], format=fmt)
            log = logging.getLogger('[flywheel/fsl-topup]')
            log.info('log level is ' + gear_context.config['gear-log-level'])
            gear_context.log_config()  # not configuring the log but logging the config
        except Exception as e:
            raise Exception("Error Setting up logger") from e


        # Now let's set up our environment from the .json file stored in the docker image:
        log.info('setting up gear environment')
        try:
            environ = set_environment(log)
            output_dir = gear_context.output_dir
            work_dir = gear_context.work_dir
            os.makedirs(work_dir, exist_ok=True)
        except Exception as e:
            raise Exception("Error setting up gear environment") from e


        # Check the inputs and categorize files
        log.info('Checking inputs')
        try:
            apply_to_files, index_list = check_inputs(gear_context)
        except Exception as e:
            raise Exception("Error with input validation") from e


        # Generate the input necessary for TOPUP
        log.info('Generating topup input')
        try:
            topup_input = generate_topup_input(gear_context)
        except Exception as e:
            raise Exception("Error generating topup inputs") from e


        # Run Topup on the inputs
        log.info('Running Topup')
        try:
            topup_out = run_topup(gear_context, topup_input)
        except Exception as e:
            raise Exception("Error running topup") from e


        # Try to apply topup to input files
        try:
            if not gear_context.config['topup_only']:
                log.info('Applying Topup Correction')
                corrected_files = apply_topup(gear_context, apply_to_files, index_list, topup_out)
        except Exception as e:
            raise Exception("Error applying topup to inputs") from e


        # Try to run topup QA
        try:
            if gear_context.config['QA']:
                log.info('Running Topup QA')
                for original, corrected in zip(apply_to_files, corrected_files):
                    report_out = mri_qa.generate_topup_report(original, corrected, work_dir)
                    report_dir, report_base = os.path.split(report_out)
                    shutil.move(report_out, os.path.join(output_dir, report_base))
        except Exception as e:
            raise Exception("Error running topup QC") from e



if __name__ == "__main__":
    main()
