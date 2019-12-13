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


##-------- Standard Flywheel Gear Structure --------##
flywheelv0 = "/flywheel/v0"
environ_json = '/tmp/gear_environ.json'

##--------    Gear Specific files/folders   --------##
mcr_root = "/opt/mcr/v90"                                              # The location of the MATLAB 2015b runtime
msot_lib = os.path.join(flywheelv0,'libs')                             # The location of the msotlib_beta_rev157 library
default_pcmm = os.path.join('/tmp','precomputed_matrix.mat')            # The location of the precomputed model matrix
run_standalone = os.path.join(flywheelv0,'run_MSOT_standalone.sh')

# Setup Flywheel client:?



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


def find_bin_file(context,log):

    # Finds the binary file associated with the .msot header for reconstruction
    # The initial assumption is that it has the same file name, but with a ".bin" extension
    # If this assumption does not hold, it looks for any file in the session with a ".bin" extension
    # If it finds a ".bin" file with a different base name, it warns the user and proceeds.
    # Otherwise it ends with an error and exits
    #
    # msot -   the .msot file used as input for the gear.  This function expects a ".bin" file with a base name
    #          identical to this input's base name
    #
    # context -The gear's context
    #
    # log -    The gear's log for tracking progress

    # get the flywheel client
    fw = context.client

    # Extract the input file's flywheel ID:
    msot = context.get_input_path('msot')
    msot_path, msot_ext = os.path.splitext(msot)
    msot_base = os.path.split(msot_path)[-1]

    msot_id = context.get_input('msot')['hierarchy']['id']
    id_type = context.get_input('msot')['hierarchy']['type']


    if not id_type == 'acquisition':
        raise Exception('.msot input file must be a file in an acquisition')

    # I tried to lookup a specific file, but was having trouble finding an API call for that, so there's this mess:
    # Get the acquisitions and extract the files:
    acq = fw.get_acquisition(acquisition_id=msot_id)
    acq_files = acq.reload().files

    match = -1

    # Loop through the files in the acquisition:
    for f in acq_files:
        f_name = f['name']
        base, ext = os.path.splitext(f_name)

        # If we find an exact match, return that immediately
        if base == msot_base and ext == ".bin":
            log.info('Found {}, continuing with computations'.format(f_name))
            match = f
            exact = True
            break

        # If we find a partial match (.bin file but not named correctly), make sure we've looked at every file
        # And then return the partial matrh
        elif ext == ".bin":
            exact = False
            match = f

    # If we found no match, exit with an error
    if match == -1:
        raise Exception('ERROR: No associated .bin file found in this subjects acquisition')

    # If we found a partial match, return that and try to run
    if not exact:
        log.warning('WARNING: Found {}, however this does not match the file base name of the .msot file: {}.  Attempting...'.format(f_name, msot_base))


    # Now try to copy in the file:
    try:
        bin_dir = os.path.join(flywheelv0, 'input', 'bin')

        if os.path.isfile(bin_dir):
            os.remove(bin_dir)

        log.debug('Making bin dir')
        os.makedirs(bin_dir, exist_ok=True)
        log.debug('Done')

        bin_file = os.path.join(bin_dir, match['name'])
        log.debug('Bin File: {}'.format(bin_file))
        log.info('Atempting to copy {} to inputs'.format(bin_file))
        acq.download_file(match['name'], bin_file)

    except Exception as e:
        context.log.fatal('Reading in associated .bin file failed', )
        context.log.exception(e)
        raise

    log.info('Success')

    # Now Collect and print out all necessary information:
    sub_id  = fw.get_subject(subject_id=acq.parents.subject).label
    sess_id = fw.get_session(session_id=acq.parents.session).label
    proj_id = fw.get_project(project_id=acq.parents.project).label
    created = match.created.ctime()
    flywheel_id = match.id
    size = match.size

    byte_to_megabyte = 1048576
    size = size / byte_to_megabyte

    flywheel_bin_path = os.path.join(proj_id,sess_id,sub_id,match['name'])
    log.info('##-------------      .bin file info      -------------##')
    log.info('.bin file used:\t{}'.format(flywheel_bin_path))
    log.info('created:\t{}'.format(created))
    log.info('flywheel id:\t{}'.format(flywheel_id))
    log.info('file size:\t{} Mb'.format(size))
    log.info('##----------------------------------------------------##')


    return bin_file


def main():
    # shutil.copy('config.json','/flywheel/v0/output/config.json')
    with flywheel.gear_context.GearContext() as gear_context:


        #### Setup logging as per SSE best practices (Thanks Andy!)
        fmt = '%(asctime)s %(levelname)8s %(name)-8s - %(message)s'
        logging.basicConfig(level=gear_context.config['gear-log-level'], format=fmt)

        log = logging.getLogger('[flywheel/MSOT-mouse-recon]')

        log.info('log level is ' + gear_context.config['gear-log-level'])

        gear_context.log_config()  # not configuring the log but logging the config

        # Now let's set up our environment from the .json file stored in the docker image:
        environ = set_environment(log)
        os.environ['MRC_ROOT'] = mcr_root # Not entirely sure if I need this
        output_dir = gear_context.output_dir

        # Now we need to extract our input files, and check if they exist
        msot = gear_context.get_input_path('msot')
        exists(msot, log)

        # Now make sure they're the correct filetype
        msot_path, msot_ext = os.path.splitext(msot)
        msot_base = os.path.split(msot_path)[-1]

        #####################################################################
        # Using the .msot input, we will look for the associated binary file:
        try:
            bin = find_bin_file(gear_context, log)
        except Exception as e:
            gear_context.log.exception(e)
            gear_context.log.fatal('bin file import failed')
            os.sys.exit(1)
        #####################################################################

        # Check if a new matrix flag was set
        pcmm = gear_context.get_input_path('matrix')

        #####################################################################
        # First make sure it exists and all that
        try:
            exists(pcmm, log, '.mat')
            exists(bin, log, '.bin')
        except Exception as e:
            gear_context.log.exception(e)
            gear_context.log.fatal('failed to locate input')
            os.sys.exit(1)
        #####################################################################

        bin_path, bin_ext = os.path.splitext(bin)
        bin_base = os.path.split(bin_path)[-1]


        if msot_ext != '.msot':
            log.error('Incorrect file type for input {}, expected .msot, got {}'.format(msot,msot_ext))
            sys.exit(1)
        if bin_ext != '.bin':
            log.error('Incorrect file type for input {}, expected .msot, got {}'.format(msot,msot_ext))
            sys.exit(1)

        if msot_base != bin_base:
            log.warning('WARNING: file names for .bin and .msot do not match.  Flywheel will rename the .bin file to match')
            log.warning('Ensure that the files are correct and from the same acquisition.  This may cause errors in the pipeline')

        shutil.copy(bin, '{}.bin'.format(msot_path))

        # The standalone code could be called here, however we're going to use the provided run_MSOT_standalone file
        # to call it for us.  This is because the run_MSOT_standalone.sh file takes a human readable call and makes it
        # into the ugly format the standalone uses.  Readable code is good code.
        log.info('Calling {} {} {} {} {} {}'.format(run_standalone, mcr_root, msot_lib, pcmm, msot, output_dir))

        #
        # result = sp.run([run_standalone, mcr_root, msot_lib, pcmm, msot, output_dir], stdout=sp.PIPE, stderr=sp.PIPE,
        #        universal_newlines=True)

        result = sp.Popen([run_standalone, mcr_root, msot_lib, pcmm, msot, output_dir], stdout=sp.PIPE, stderr=sp.PIPE,
               universal_newlines=True, shell=False)


        while True:
            line = result.stdout.readline()
            if not line: break
            else:
                log.info(line)

        if result.poll() != 0:
            er = result.stderr.read()
            log.info(er)
            raise Exception(er)
        else:
            log.info('Completed successfully')


# This could all be smarter, especially with error/exception handling.
if __name__ == "__main__":
    main()