import os
import datetime
import pickle
import subprocess
import sys
import math
import warnings
from warnings import warn
from collections import OrderedDict
import shutil
import csv

import numpy as np

from .edisonbatch import Srun, Batch
from . import inputfiles
from .inputfiles import QuaLiKizRun, Ion, IonList, Electron

warnings.simplefilter('always', UserWarning)
class PathException(Exception):
    def __init__(self, path):
        message = path + ' must be an absolute path or bad things will happen!'
        super().__init__(message)

class Run:
    """ A collection of QuaLiKiz Jobs
    This class is used to define a collection of QuaLiKiz Jobs, or in
    other words a collection of sbatch scripts and their input.

    Class variables:
        - scriptname:  The default name of the sbatch scripts
    """
    # pylint: disable=too-few-public-methods

    scriptname = 'edison.sbatch'
    def __init__(self, rootdir, qualikizdir="", runsdir=""):
        """ Initialize a run
        Arguments:
            - rootdir: Directory of the QuaLiKiz root repo.

        Keyword arguments:
            - runsdir:     Directory of the QuaLiKiz runs dir. Runs will be
                           created in this folder. Usually derived from
                           the rootdir
            - qualikizdir: Directory of the QuaLiKiz python tools. Usually
                           derived from the rootdir
        """
        self.jobs = {}
        if os.path.isabs(rootdir):
            self.rootdir = rootdir
        else:
            raise PathException('rootdir')

        if qualikizdir == "":
            self.qualikizdir = os.path.join(rootdir, 'tools/qualikiz')
        else:
            self.qualikizdir = qualikizdir

        if runsdir == "":
            self.runsdir = os.path.join(rootdir, 'runs')
        else:
            self.runsdir = runsdir

        if not os.path.isabs(self.qualikizdir):
            raise PathException('qualikizdir')

        if not os.path.isabs(self.runsdir):
            raise PathException('runsdir')

    def to_file(self, overwrite=False):
        """ Writes all Run folders to file. """
        # pylint: disable=invalid-name, unused-variable
        for __, job in self.jobs.items():
            job.to_file(self.runsdir, self.qualikizdir, overwrite=overwrite)


class EmptyJob:
    jobdatafile = 'jobdata.pkl'
    metadatafile = 'metadata.csv'
    """ Defines an empty QuaLiKiz Job, so no input files are generated"""
    # pylint: disable=too-few-public-methods, too-many-arguments

    def __init__(self, rootdir, name, binary_basename, batch,
                 parameters_script=""):
        """ Initialize an empty QuaLiKiz job
        Arguments:
            - rootdir:         Path of the QuaLiKiz root. Usually get this
                               from Run instance
            - name:            The name of the QuaLiKiz Job. This will be the
                               name of the folder that will be generated
            - binary_basename: The name of the binary that needs to be run.
                               Relative to the batch script file
            - batch:           An instance of the Batch script

        Keyword arguments:
            - parameters_script: A string with the script used to 
                                 create the input files
        """
        if os.path.isabs(rootdir):
            self.binary_path = os.path.abspath(os.path.join(rootdir,
                                                        binary_basename))
        else:
            raise PathException('rootdir')

        self.parameters_script = parameters_script
        self.name = name
        self.batch = batch

    def to_file(self, runsdir, qualikizdir, overwrite=False, metapickle=True):
        """ Write all Job folders to file
        This generates a folder for each Job. Each Job has its own sbatch script.
        This will also generate all folders and links needed for QuaLiKiz to run.

        Arguments:
            - runsdir:     Directory to which to write the Jobs
            - qualikizdir: Directory of the qualikiz python module

        Keyword arguments:
            - overwrite:  Overwrite the directory if it exists. Default=False
            - metapickle: Dump the Job data to file. This is needed if you
                          want to recreate or analyze the job later. Default=True
        """
        if not os.path.isabs(qualikizdir):
            raise PathException('qualikizdir')

        if not os.path.isabs(runsdir):
            raise PathException('runsdir')

        if not os.path.isdir(runsdir):
            os.mkdir(runsdir)

        path = os.path.abspath(os.path.join(runsdir, self.name))
        try:
            os.mkdir(path)
        except FileExistsError:
            if not overwrite:
                resp = input('folder exists, overwrite? [Y/n]')
                if resp == '' or resp == 'Y' or resp == 'y':
                    overwrite = True
            if overwrite:
                print ('overwriting')
                shutil.rmtree(path)
                os.mkdir(path)
            else:
                print ('aborting')
                return 1
        if not os.path.exists(self.binary_path):
            warn('Warning! Binary at ' + self.binary_path + ' does not ' +
                 'exist! Run will fail!')
        os.symlink(self.binary_path,
                   os.path.join(path, os.path.basename(self.binary_path)))
        os.symlink(qualikizdir,
                   os.path.join(path, 'qualikiz'))
        os.makedirs(os.path.join(path, 'output/primitive'), exist_ok=True)
        os.makedirs(os.path.join(path, 'debug'), exist_ok=True)
        self.batch.to_file(path=os.path.join(path, Run.scriptname))
        if self.parameters_script == "":
            with open(os.path.join(qualikizdir,
                                   'parameters_template.py')) as file_:
                parameters_script = file_.readlines()
        else:
            parameters_script = self.parameters_script
        with open(os.path.join(path, 'parameters.py'), 'w') as file_:
              file_.writelines(parameters_script)

        if metapickle:
            with open(os.path.join(path, 'jobdata.pkl'), 'wb') as file_:
                pickle.dump(self, file_)

def recursive_function(path, function, dotprint=False):
    """ Recursively run a function in a specific directory
    Only run the function if it has a valid run script Run.scriptname.
    Arguments:
        - path: Path to recursively run a funciton in
        - function: The function to recursively run. The function should
                accept only a path as input

    Keyword arguments:
        - dotprint: Print a dot (no newline) after echt directory
    """
    results = []
    if Run.scriptname in os.listdir(path):
        try:
            results.append(function(path))
        except Exception as e:
            warn(e)
            warn('found exception during recursive run. Skipping..')
    else:
        for folder in os.listdir(path):
            job_folder = os.path.join(path, folder)
            if os.path.isdir(job_folder):
                if Run.scriptname in os.listdir(job_folder):
                    try:
                        results.append(function(job_folder))
                    except Exception as e:
                        warn(e)
                        warn('found exception during recursive run. Skipping..')
                    if dotprint:
                        print ('.', end='', flush=True)
    return results

def generate_input(job_folder):
    """ Generate input for a job in a specific directory """
    cmd = ['python', os.path.abspath(os.path.join(job_folder, 'parameters.py'))]
    subprocess.check_call(cmd)

def run_job(job_folder):
    """ Run a job in a specific directory """
    input_binary = os.path.join(job_folder, 'input/p1.bin')
    if not os.path.exists(input_binary):
        warn('Warning! Input binary at ' + input_binary + ' does not ' +
             'exist! Run will fail! Please generate input binaries with ' +
             'parameters.py')


    cmd = 'git describe --tags'
    describe = subprocess.check_output(cmd, shell=True)
    qualikiz_version = describe.strip().decode('utf-8')

    cmd = 'sbatch --workdir=' + job_folder + ' ' + os.path.join(job_folder, Run.scriptname)
    output = subprocess.check_output(cmd, shell=True)
    jobnumber = output.split()[-1].decode('utf-8')
    
    # Dump some important profiling stuff to file
    with open(os.path.join(job_folder, EmptyJob.metadatafile), 'w', newline='') as file_:
        writer = csv.writer(file_)
        writer.writerow(['jobnumber', jobnumber])
        writer.writerow(['submittime', datetime.datetime.now()])
        writer.writerow(['qualikiz_version', qualikiz_version])
    print (jobnumber)
