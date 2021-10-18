"""
This module, utils.args.common, hosts the functionality used by all modules in
utils.args. They streamline the 'execute' functionality of the build/validate/execute
paradigm followed in each of the other module-scripts in args.
"""

import os, os.path as op
import subprocess as sp
import re
import logging
log = logging.getLogger()


def build_command_list(command, ParamList, include_keys=True):
    """
    command is a list of prepared commands
    ParamList is a dictionary of key:value pairs to be put into the command
     list as such ("-k value" or "--key=value")
    include_keys indicates whether to include the key-names with the command (True)
    """
    for key in ParamList.keys():
        # Single character command-line parameters are preceded by a single '-'
        if len(key) == 1:
            if include_keys:
                # If Param is boolean and true include, else exclude
                if type(ParamList[key]) == bool or len(str(ParamList[key])) == 0:
                    if ParamList[key] and include_keys:
                        command.append('-' + key)
                else:
                    command.append('-' + key)
                    command.append(str(ParamList[key]))
        # Multi-Character command-line parameters are preceded by a double '--'
        else:
            # If Param is boolean and true include, else exclude
            if type(ParamList[key]) == bool:
                if ParamList[key] and include_keys:
                    command.append('--' + key)
            else:
                # If Param not boolean, but without value include without value
                # (e.g. '--key'), else include value (e.g. '--key=value')
                item = ""
                if include_keys:
                    item = '--' + key
                if len(str(ParamList[key])) > 0:
                    if include_keys:
                        item = item + "="
                    item = item + str(ParamList[key])
                command.append(item)
    return command


def exec_command(command, shell=False, stdout_msg=None, cont_output=False):
    """
    This is a generic abstraction to execute shell commands using the subprocess
    module. Parameters are
    - context: the gear context. Used for the environment and dry-run flags
    - command: list of command-line parameters, starting with the command to run
    - shell: whether or not to execute as a single shell string, redirects
    - stdout_msg: Used to indicate whether the output is redirected
    - cont_output: Used to provide continuous output of stdout without waiting
                   until the completion of the shell command
    """
    log.info('Executing command: \n' + ' '.join(command) + '\n\n')

    if shell:
        run_command = ' '.join(command)
    else:
        run_command = command

    result = sp.Popen(run_command, stdout=sp.PIPE, stderr=sp.PIPE,
                      universal_newlines=True, shell=shell)

    # log that we are using an alternate stdout message
    if stdout_msg != None:
        log.info(stdout_msg)

    # if continuous stdout is desired... and we are not redirecting output
    if cont_output and not (shell and ('>' in command)) \
            and (stdout_msg == None):
        while True:
            stdout = result.stdout.readline()
            if stdout == '' and result.poll() is not None:
                break
            if stdout:
                log.info(stdout)
        returncode = result.poll()

    else:
        stdout, stderr = result.communicate()
        returncode = result.returncode
        if stdout_msg != None:
            log.info(stdout)

    log.info('Command return code: {}'.format(returncode))

    if result.returncode != 0:
        log.error('The command:\n ' +
                  ' '.join(command) +
                  '\nfailed. with:\n' +
                  stderr)
        raise Exception(stderr)