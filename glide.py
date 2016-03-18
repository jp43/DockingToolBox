import os
import sys
import glob
import shutil
import subprocess

import util.check_license as chkl
import util.pdbtools as pdbt

required_programs = ['prepwizard', 'glide', 'ligprep', 'glide_sort', 'pdbconvert']

default_settings = {'actxrange': '30.0', 'actyrange': '30.0', 'actzrange': '30.0', \
'innerbox': '10, 10, 10', 'poses_per_lig': '10', 'pose_rmsd': '0.5', 'precision': 'SP', 'tmpdir': None}

known_settings = {'herg': {'grid_center': '3.966, 8.683, 11.093'}, \
'herg-cut': {'grid_center': '3.966, 8.683, 11.093'}, \
'herg-inactivated': {'grid_center': '0.000, 0.000, -5.000'}}

required_settings_names = ['grid_center']

def write_docking_script(filename, input_file_r, input_file_l, config):

    outerbox = config.options['glide']['actxrange'] + ', ' + \
               config.options['glide']['actyrange'] + ', ' + \
               config.options['glide']['actzrange']

    # prepare protein
    prepwizard_cmd = chkl.eval("prepwizard -WAIT -fix %(input_file_r)s target.mae"%locals(), 'glide') # receptor prepare

    # prepare grid
    glide_grid_cmd = chkl.eval("glide -WAIT grid.in", 'glide') # grid prepare
    structconvert_cmd = chkl.eval("structconvert %(input_file_l)s lig.mae"%locals(), 'glide')

    # docking cmd
    glide_dock_cmd = chkl.eval("glide -WAIT dock.in", 'glide') # docking command
    glide_sort_cmd = chkl.eval("glide_sort -r sort.rept dock_pv.maegz -o dock_sorted.mae", 'glide') # cmd to extract results

    if config.options['glide']['tmpdir']:
        tmpdirline = "export SCHRODINGER_TMPDIR=%(tmpdir)s"%config.options['glide']
    else:
        tmpdirline = ""

    # write vina script
    with open(filename, 'w') as file:
        script ="""#!/bin/bash
%(tmpdirline)s

# (A) Prepare receptor
%(prepwizard_cmd)s

# (B) Prepare grid
echo "USECOMPMAE YES
INNERBOX %(innerbox)s
ACTXRANGE %(actxrange)s
ACTYRANGE %(actyrange)s
ACTZRANGE %(actzrange)s
GRID_CENTER %(grid_center)s
OUTERBOX %(outerbox)s
ENTRYTITLE target
GRIDFILE grid.zip
RECEP_FILE target.mae" > grid.in
%(glide_grid_cmd)s

# (C) convert ligand to maestro format
%(structconvert_cmd)s

# (D) perform docking
echo "WRITEREPT YES
USECOMPMAE YES
DOCKING_METHOD confgen
SAMPLE_RINGS False
POSES_PER_LIG %(poses_per_lig)s
POSE_RMSD %(pose_rmsd)s
GRIDFILE $PWD/grid.zip
LIGANDFILE $PWD/lig.mae
PRECISION %(precision)s" > dock.in

%(glide_dock_cmd)s

%(glide_sort_cmd)s"""%dict(dict(locals()).items()+config.options['glide'].items())
        file.write(script)

def extract_docking_results(file_r, file_l, file_s, config):

    subprocess.call(chkl.eval("pdbconvert -brief -imae dock_sorted.mae -opdb dock_sorted.pdb", 'glide', redirect='/dev/null'), shell=True)
    shutil.copyfile(config.input_file_r, file_r)

    ## write file with receptor
    #with open('dock_sorted-1.pdb', 'r') as ffin:
    #    with open(file_r, 'w') as ffout:
    #        line = ffin.next()
    #        while not line.startswith('MODEL'):
    #            line = ffin.next()
    #        ffout.write(line)
    #        for line in ffin:
    #            ffout.write(line)

    if config.extract == 'lowest':
        # write file with ligand
        with open(file_l, 'w') as ffout:
            with open('dock_sorted-2.pdb', 'r') as ffin:
                line = ffin.next()
                while not line.startswith('MODEL'):
                    line = ffin.next()
                ffout.write(line)
                for line in ffin:
                    ffout.write(line)
    elif config.extract == 'all':
        # write file with ligand
        with open(file_l, 'w') as ffout:
            idxs = []
            for pdbfile in glob.glob('dock_sorted-*.pdb'):
                idxs.append(int((pdbfile.split('-')[1]).split('.')[0]))
            maxidx = max(idxs)
            for idx in range(1,maxidx):
                with open('dock_sorted-%s.pdb'%(idx+1), 'r') as ffin:
                    line = ffin.next()
                    while not line.startswith('MODEL'):
                        line = ffin.next()
                    ffout.write('MODEL     %s\n'%idx)
                    for line in ffin:
                        if line.startswith('ENDMDL') or not line.startswith('END'):
                            ffout.write(line)
            ffout.write('END')

    # extract scores
    with open('dock.rept', 'r') as ffin:
        with open(file_s, 'w') as ffout:
            line = ffin.next()
            while not line.startswith('===='):
                line = ffin.next()
            while True:
                line = ffin.next()
                if line.strip():
                    print >> ffout, line.split()[2]
                    if config.extract == 'lowest':
                        break
                else:
                    break

def cleanup(config):
    for ff in glob.glob('dock_sorted*.pdb'):
        os.remove(ff)
