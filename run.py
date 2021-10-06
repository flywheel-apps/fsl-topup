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



#### Setup logging as per SSE best practices
try:

    FORMAT = "[ %(asctime)8s%(levelname)8s%(filename)s:%(lineno)s - %(funcName)8s() ] %(message)s"
    logging.basicConfig(format=FORMAT)
    log = logging.getLogger()
except Exception as e:
    raise Exception("Error Setting up logger") from e



##-------- Standard Flywheel Gear Structure --------##
flywheelv0 = "/flywheel/v0"
environ_json = '/tmp/gear_environ.json'


##--------    Gear Specific files/folders   --------##
DEFAULT_CONFIG = '/flywheel/v0/b02b0.cnf'

def set_environment(log):
    """Sets up the docker environment saved in a environment.json file

    Args:
        log (class:`logging.Logger`):

    Returns:
        environ (json): the environment variables in json format
    """



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

def is4D(image):
    """Checks to see if a given image is 4D

    Args:
        image (str): path to image

    Returns:
        (bool): true if image is 4d, false otherwise.

    """
    shape = nb.load(image).header.get_data_shape()
    if len(shape) < 4:
        return(False)
    elif shape[3] > 1:
        return(True)
    else:
        return(False)


def check_inputs(context):
    """Check gear inputs

    Checks the inputs of the gear and determines TOPUP run settings, and generates a list of files to apply TOPUP to
    (if indicated by the user)

    Args:
        context (class: `flywheel.gear_context.GearContext`): flywheel gear context

    Returns:
        apply_to_files (list): a list of files to apply the TOPUP correction to after calculating the TOPUP fieldmaps
        index_list (list): the row index in the acquisition_parameters file associated with each file in apply_to_files
    """



    apply_to_files = []

    # Capture all the inputs from the gear context
    image1_path = context.get_input_path('image_1')
    image2_path = context.get_input_path('image_2')
    config_path = context.get_input_path('config_file')
    apply_to_a = context.get_input_path('apply_to_1')
    apply_to_b = context.get_input_path('apply_to_2')
    acq_par = context.get_input_path('acquisition_parameters')

    # If image_1 is 4D, we will apply topup correction to the entire series after running topup
    if is4D(image1_path):
        apply_to_files.append((image1_path, '1')) # '1' Referring to the row this image is associated with in the "acquisition_parameters" file
        log.info('Will run applytopup on {}'.format(image1_path))

    # If image_2 is 4D, we will apply topup correction to the entire series after running topup
    if is4D(image2_path):
        apply_to_files.append((image2_path,'2'))
        log.info('Will run applytopup on {}'.format(image2_path))

    # If apply_to_a is provided, applytopup to this image, too.
    # NOTE that apply_to_a must correspond to row 1 in the acquisition_parameters file
    if apply_to_a:
        apply_to_files.append((apply_to_a,'1'))
        log.info('Will run applytopup on {}'.format(apply_to_a))

    # If apply_to_b is provided, applytopup to this image, too.
    # NOTE that apply_to_b must correspond to row 2 in the acquisition_parameters file
    if apply_to_b:
        apply_to_files.append((apply_to_b,'2'))
        log.info('Will run applytopup on {}'.format(apply_to_b))

    # Read in the parameters and print them to the log
    parameters = open(acq_par, 'r')
    log.info(parameters.read())
    parameters.close()


    if config_path:
        log.info('Using config settings in {}'.format(config_path))
    else:
        log.info('Using default config values')

    return (apply_to_files)


def generate_topup_input(context):
    """Takes gear input files and generates a merged input file for TOPUP.

    Args:
        context (class: `flywheel.gear_context.GearContext`): flywheel gear context

    Returns:
        merged (string): the path to the merged file for use in TOPUP

    """



    # Capture the paths of the input files from the gear context
    image1_path = context.get_input_path('image_1')
    image2_path = context.get_input_path('image_2')
    work_dir = context.work_dir

    # Create a base directory in the context's working directory for image 1
    base_out1 = os.path.join(work_dir, 'Image1')

    # If image 1 is 4D, we will only use the first volume (Assuming that a 4D image is fMRI and we only need one volume)
    # TODO: Allow the user to choose which volume to use for topup correction
    if is4D(image1_path):
        im_name = os.path.split(image1_path)[-1]
        log.info('Using volume 1 in 4D image {}'.format(im_name))

        # Generate a command to extract the first volume
        cmd = ['fslroi', image1_path, base_out1, '0', '1']
    else:
        # If the image is 3D, simply copy the image to our working directory using fslmaths because it's extension agnostic
        cmd = ['fslmaths', image1_path, base_out1]

    # Execute the command, resulting in a single volume from image_1 in the working directory
    exec_command(cmd)

    # Repeat the same steps with image 2
    base_out2 = os.path.join(work_dir, 'Image2')
    if is4D(image2_path):
        im_name = os.path.split(image2_path)[-1]
        log.info('Using volume 1 in 4D image {}'.format(im_name))

        cmd = ['fslroi', image2_path, base_out2, '0', '1']
    else:
        cmd = ['fslmaths', image2_path, base_out2]
    exec_command(cmd)

    # Merge the two volumes (image_1 then image_2)
    merged = os.path.join(work_dir, 'topup_vols')
    cmd = ['fslmerge', '-t', merged, base_out1, base_out2]
    exec_command(cmd)

    return (merged)


def run_topup(context, input):
    """Runs topup on a given input image.

    Requires acquisition parameters and input options from the gear context.

    Args:
        context (class: `flywheel.gear_context.GearContext`): flywheel gear context
        input (string): the path to the input file for topup's 'imain' input option

    Returns:
        out (string): the topup root path

    """



    # Get the output directory and config file from the gear context
    output_dir = context.output_dir
    config_path = context.get_input_path('config_file')
    acq_par = context.get_input_path('acquisition_parameters')

    # If the user didn't provide a config file, use the default
    if not config_path:
        config_path = DEFAULT_CONFIG

    # Setup output directories
    fout = os.path.join(output_dir, 'topup-fmap')
    iout = os.path.join(output_dir, 'topup-input-corrected')
    out = os.path.join(output_dir, 'topup')
    logout = os.path.join(output_dir, 'topup-log.txt')

    # Get output options from the gear context (which commands to include in the topup call)
    dfout = context.config['displacement_field']
    jacout = context.config['jacobian_determinants']
    rbmout = context.config['rigid_body_matrix']
    verbose = context.config['verbose']
    debug = context.config['topup_debug_level']
    # lout = context.config['mystery_output']

    # Begin generating the command arguments with the default commands that are always present
    argument_dict = {'imain': input, 'datain': acq_par, 'out': out, 'fout': fout,
                     'iout': iout, 'logout': logout, 'config': config_path}

    # Add the optional commands defined by the user in the config settings
    if dfout:
        argument_dict['dfout'] = out + '-dfield'
    if jacout:
        argument_dict['jacout'] = out + '-jacdet'
    if rbmout:
        argument_dict['rbmout'] = out + '-rbmat'
    if verbose:
        argument_dict['verbose'] = True
    if debug:
        argument_dict['debug'] = debug

    # Print the config file settings to the log
    log.info('Using config settings:\n\n{}\n\n'.format(open(config_path, 'r').read()))

    # Build the command and execute
    command = build_command_list(['topup'], argument_dict)
    exec_command(command)

    return (out)


def apply_topup(context, apply_topup_files, topup_out):
    """Applies a calculated topup correction to a list of files.

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
    # Get the acquisition parameter file for the "--datain" option of topup
    acq_par = context.get_input_path('acquisition_parameters')
    output_files = []

    # For all the files we're applying topup to, loop through them with their associated row in the acquisition parameter file
    for fl, ix in apply_topup_files:

        # Generate an output name: "topup_corrected_" appended to the front of the original filename
        base = os.path.split(fl)[-1]
        output_file = os.path.join(context.output_dir, 'topup-corrected-{}'.format(base))
        output_files.append(output_file)

        # Generate the applytopup command
        cmd = ['applytopup',
               '--imain={}'.format(fl),
               '--datain={}'.format(acq_par),
               '--inindex={}'.format(ix),
               '--topup={}'.format(topup_out),
               '--method=jac',
               '--interp=spline',
               '--out={}'.format(output_file)]

        # Execute the command
        exec_command(cmd)

    return (output_files)


def main():
    """Main TOPUP correction script

    This script runs TOPUP on two images provided in the gear. It will apply the calculated topup correction to the
    inputs, as well as two additional files you provide, "apply_to_1" and "apply_to_2".  The image "apply_to_1" must
    have the same PE direction as "Image_1", and "apply_to_2" must have the same PE direction as "Image_2".

    Returns: None

    """

    # shutil.copy('config.json','/flywheel/v0/output/config.json')
    with flywheel.gear_context.GearContext() as gear_context:
        log.setLevel(gear_context.config['gear-log-level'])

        gear_context.log_config()  # not configuring the log but logging the config

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
            apply_to_files = check_inputs(gear_context)
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
                corrected_files = apply_topup(gear_context, apply_to_files, topup_out)
        except Exception as e:
            raise Exception("Error applying topup to inputs") from e


        #TODO: Make this run on the input images, PLUS any corrected images

        # Try to run topup QA
        # apply_to_files is currently a list of [(filename, index), ... ].  We need to combine this
        # with corrected files so that we have [(original file, corrected file), ... ]
        file_comparison = [(apply_to_files[i][0], corrected_files[i]) for i in range(len(corrected_files))]

        try:
            if gear_context.config['QA']:
                log.info('Running Topup QA')
                for original, corrected in file_comparison:
                    report_out = mri_qa.generate_topup_report(original, corrected, work_dir)
                    report_dir, report_base = os.path.split(report_out)
                    shutil.move(report_out, os.path.join(output_dir, report_base))

                    # Move the config file used in the analysis to the output
                    config_path = gear_context.get_input_path('config_file')

                    # If this wasn't provided as input, save to output for provenance.
                    if not config_path:
                        config_path = DEFAULT_CONFIG
                        config_out = os.path.join(output_dir, 'config_file.txt')
                        if os.path.exists(config_path):
                            shutil.move(config_path, config_out)
                        else:
                            log.info(f'no path {config_path}')


        except Exception as e:
            raise Exception("Error running topup QC") from e



if __name__ == "__main__":
    main()
