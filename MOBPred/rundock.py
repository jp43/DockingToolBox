#!/usr/bin/python
from __future__ import with_statement

import sys
import os
import shutil
import argparse
import ConfigParser
import time
import pandas as pd
from glob import glob

from mdtools.utility import mol2

import setup
import rescoring

class DockingConfig(object):

    def __init__(self, args):

        # check if config file exist
        if not os.path.exists(args.config_file):
            raise ValueError("Config file %s not found!"%(args.config_file))

        config = ConfigParser.SafeConfigParser()
        config.read(args.config_file)

        # prepare ligand file
        file_l = os.path.abspath(args.input_file_l)
        new_file_l = os.path.basename(file_l)
        pref, ext = os.path.splitext(new_file_l)
        new_file_l = pref + '_uniq' + ext

        # create a ligand file with unique atom names
        mol2.update_mol2file(file_l, new_file_l, unique=True)
        self.input_file_l = os.path.abspath(new_file_l)

        # check if ligand file exists
        if not os.path.exists(self.input_file_l):
            raise IOError("File %s not found!"%(self.input_file_l))

        self.input_file_r = os.path.abspath(args.input_file_r)

        # check if receptor file exists
        if not os.path.exists(self.input_file_r):
            raise IOError("File %s not found!"%(self.input_file_r))

        self.docking = setup.DockingSetup(config)
        self.extract_only = args.extract_only
        self.rescoring = rescoring.Rescoring(config, args)

class Docking(object):

    def create_arg_parser(self):
        parser = argparse.ArgumentParser(description="""rundock : dock with multiple softwares --------
Requires one file for the ligand (1 struct.) and one file for the receptor (1 struct.)""")

        parser.add_argument('-l',
            type=str,
            dest='input_file_l',
            required=True,
            help = 'Ligand coordinate file(s): .mol2')

        parser.add_argument('-r',
            type=str,
            dest='input_file_r',
            required=True,
            help = 'Receptor coordinate file(s): .pdb')

        parser.add_argument('-f',
            dest='config_file',
            required=True,
            help='config file containing docking parameters')

        parser.add_argument('-d',
            dest='posedir',
            default='poses',
            help='Directory containing poses to rescore (should be used with rescore_only option)')

        parser.add_argument('-extract_only',
            dest='extract_only',
            action='store_true',
            default=False,
            help='Extract structures only (usually used for debugging purposes)')

        parser.add_argument('-prepare_only',
            dest='prepare_only',
            action='store_true',
            help='Only prepare scripts for docking (do not run docking)')

        parser.add_argument('-rescore_only',
            dest='rescore_only',
            action='store_true',
            default=False,
            help='Run rescoring only')

        return parser

    def finalize(self, config, config_d):
        """create directory containing all the poses found!"""

        resultdir = 'poses'
        shutil.rmtree(resultdir, ignore_errors=True)
        os.mkdir(resultdir)

        nposes = [1] # number of poses involved for each binding site
        sh = 1 # shift of model

        info = {}
        features = ['program', 'nposes', 'firstidx', 'site']
        for ft in features:
            info[ft] = []

        for kdx in range(len(config_d.site)):
            bs = config_d.site['site'+str(kdx+1)] # current binding site
            for name, program, options in config_d.instances:
                # find name for docking directory
                instdir = '%s'%name
                if bs[0]:
                    instdir += '.' + bs[0]                
                poses_idxs = []
                for filename in glob(instdir+'/lig-*.mol2'):
                    poses_idxs.append(int((filename.split('.')[-2]).split('-')[-1]))
                poses_idxs = sorted(poses_idxs)
                idx = -1
                for idx, pose_idx in enumerate(poses_idxs):
                    shutil.copyfile(instdir+'/lig-%s.mol2'%pose_idx, resultdir+'/lig-%s.mol2'%(idx+sh))

                # update info
                info['program'].append(name)
                info['nposes'].append(idx+1)
                info['firstidx'].append(sh)
                info['site'].append(bs[0])

                # update shift
                sh += idx + 1
            nposes.append(sh)

        # write info
        info = pd.DataFrame(info)
        info[features].to_csv(resultdir+'/info.dat', index=False)

        # insert line at the beginning of the info file
        with open(resultdir+'/info.dat', 'r+') as ff:
            content = ff.read()
            ff.seek(0, 0)
            line = '#' + ','.join(map(str,nposes))+'\n'
            ff.write(line.rstrip('\r\n') + '\n' + content)

        # copy receptor in folder
        shutil.copyfile(config.input_file_r, resultdir+'/rec.pdb')

    def run_docking(self, config, args):
        """Running docking simulations using each program specified..."""

        if not args.prepare_only:
            tcpu1 = time.time()

        config_d = config.docking
        # iterate over all the binding sites
        for kdx in range(len(config.docking.site)):
            for instance, program, options in config.docking.instances: # iterate over all the instances

                # get docking class
                DockingClass = getattr(sys.modules[program], program.capitalize())

                # create docking instance and run docking
                DockingInstance = DockingClass(instance, config.docking.site['site'+str(kdx+1)], options)
                DockingInstance.run_docking(config.input_file_r, config.input_file_l, minimize=config_d.minimize, cleanup=config_d.cleanup, \
extract_only=config.extract_only, prepare_only=args.prepare_only)

        if not args.prepare_only:
            self.finalize(config, config_d)
            tcpu2 = time.time()
            print "Docking procedure done. Total time needed: %i s" %(tcpu2-tcpu1)

    def run(self):

        parser = self.create_arg_parser()
        args = parser.parse_args()    

        print "Setting up parameters..."
        config = DockingConfig(args)

        # run docking
        if not config.rescoring.rescore_only:
            self.run_docking(config, args)

        # run rescoring
        if config.rescoring.is_rescoring and not args.prepare_only:
            config.rescoring.run(config.input_file_r, args.posedir)
