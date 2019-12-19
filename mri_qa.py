#!/usr/bin/env python3

import os
import subprocess as sp
import logging
import flywheel
import matplotlib.pyplot as pl
import matplotlib.image as mpm

fsldir='/usr/lib/fsl/5.0'

def bet(image,workdir='',shell=False):

    if workdir == '':
        workdir = '/Users/davidparker/Documents/Flywheel/SSE/MyWork/Gears/Topup/Gear/work'

    shell=True
    com_cmd=['{}/fslstats'.format(fsldir),image, '-C']
    print(' '.join(com_cmd))
    com_cmd=' '.join(com_cmd)

    result = sp.Popen(com_cmd, stdout=sp.PIPE, stderr=sp.PIPE,
                      universal_newlines=True, shell=shell)

    out,err=result.communicate()
    center_of_mass=out.rstrip()

    bet_out=os.path.join(workdir,'bet')
    bet_cmd = ['{}/bet2'.format(fsldir),image,bet_out,'-o', '-m', '-t','-f','0.5','-w','0.4','-c',center_of_mass]
    print(' '.join(bet_cmd))
    bet_cmd = ' '.join(bet_cmd)
    result = sp.Popen(bet_cmd, stdout=sp.PIPE, stderr=sp.PIPE,
                      universal_newlines=True, shell=shell)

    out, err = result.communicate()
    print(out)
    print(err)


    return(bet_out)


def bet_2_outline(original,bet_root,shell=False):

    overlay = bet_root+'_overlay.nii.gz'
    diff_out = bet_root+'_diff'

    cmd = ['fslmaths', overlay,'-sub',original,diff_out]
    print(' '.join(cmd))
    result = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE,
                      universal_newlines=True, shell=shell)
    out, err = result.communicate()
    print(out)
    print(err)

    cmd = ['fslstats', diff_out, '-p', '97']
    print(' '.join(cmd))
    result = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE,
                      universal_newlines=True, shell=shell)
    out, err = result.communicate()
    print(out)
    print(err)

    thresh = out.rstrip()

    thresh_out = bet_root+'_thresh'
    cmd = ['fslmaths',diff_out,'-thr',thresh,thresh_out]
    print(' '.join(cmd))
    result = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE,
                      universal_newlines=True, shell=shell)
    out, err = result.communicate()
    print(out)
    print(err)

    bin_out = bet_root+'_outline'
    cmd = ['fslmaths', thresh_out, '-bin', bin_out]
    print(' '.join(cmd))
    result = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE,
                      universal_newlines=True, shell=shell)
    out, err = result.communicate()
    print(out)
    print(err)

    os.remove(thresh_out+'.nii.gz')
    os.remove(diff_out+'.nii.gz')

    return(bin_out)


def erode_mask(mask,out,shell=False):
    cmd = ['fslmaths',mask,'-ero','-sub',mask,'-mul','-1']

def overlay(image1,image2,output,shell=False):
    cmd=['overlay','0','0',image1,'-a',image2,'0.001','5',output]
    print(' '.join(cmd))
    result = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE,
                      universal_newlines=True, shell=shell)

    out, err = result.communicate()
    print(out)
    print(err)

    wrkdir = os.path.split(output)[0]

    cmd=['slicer',output,'-c','-s','3',
         '-x','0.5',os.path.join(wrkdir,'x0v.png'),
         '-y','0.5',os.path.join(wrkdir,'y0v.png'),
         '-z','0.5',os.path.join(wrkdir,'z0v.png'),]

    print(' '.join(cmd))
    result = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE,
                      universal_newlines=True, shell=shell)

    out, err = result.communicate()
    print(out)
    print(err)

    cmd=['{}/pngappend'.format(fsldir),os.path.join(wrkdir,'x0v.png'),'+','4',
         os.path.join(wrkdir,'y0v.png'),'+','4',
         os.path.join(wrkdir,'z0v.png'),output+'.png']

    print(' '.join(cmd))
    result = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE,
                      universal_newlines=True, shell=shell)

    out, err = result.communicate()
    print(out)
    print(err)


def outline_overlay(background='', outline='', name=''):

    bg_dir, bg_base = os.path.split(background)
    ol_dir, ol_base = os.path.split(outline)

    if name == '':
        bg_root = bg_base[:bg_base.find('.nii')]
        ol_root = ol_base[:ol_base.find('.nii')]
        name = '{}_on_{}'.format(ol_root, bg_root)
        work_base = bg_dir
    else:
        work_base = os.path.split(name)[0]

    workdir = os.path.join(work_base, 'outline_work')
    os.makedirs(workdir, exist_ok=True)

    bet_out = bet(outline, workdir)

    mask_outline = bet_2_outline(outline, bet_out, shell=False)
    overlay(background, mask_outline, name, shell=False)


def plot_overlays(files, titles, output):
    log = logging.getLogger('[flywheel/fsl-topup/mri_qa/plot_overlays]')
    if not len(files) == len(titles):
        log.warning('Number of files different than number of provided titles')
        return

    f, ax = pl.subplots(len(files), 1)

    for ai, a in enumerate(ax):
        file = files[ai]
        title = titles[ai]
        image = mpm.imread(file+'.png')
        a.imshow(image)
        a.set_title(title)
        a.set_xticks([])
        a.set_yticks([])

    pl.tight_layout()

    pl.savefig(output)
    pl.close()

def generate_topup_report(original_image, corrected_image, output_base=''):
    log = logging.getLogger('[flywheel/fsl-topup/mri_qa/generate_topup_report]')

    path, original_base = os.path.split(original_image)

    if output_base == '':
        output_base = path

    original_base = original_base[:original_base.find('.nii.gz')]

    log.info('overlay 1')
    name1 = os.path.join(output_base,'corrected_over_original')
    outline_overlay(original_image, corrected_image, name1)

    log.info('overlay 2')
    name2 = os.path.join(output_base,'original_over_corrected')
    outline_overlay(corrected_image, original_image, name2)

    log.info('generating report')
    report_out = os.path.join(output_base,'{}_QA_report.png'.format(original_base))
    plot_overlays([name1, name2], ['topup (red) over original', 'original (red) over topup'], report_out)
    return(report_out)


if __name__ == '__main__':

    background = '/Users/davidparker/Documents/Flywheel/SSE/MyWork/Gears/Topup/Gear/work/Image1.nii.gz'
    outline = '/Users/davidparker/Documents/Flywheel/SSE/MyWork/Gears/Topup/Gear/output/topup_corrected_nodif.nii.gz'
    name1 = '/Users/davidparker/Documents/Flywheel/SSE/MyWork/Gears/Topup/Gear/work/topup_over_orig'
    outline_overlay(background, outline, name1)

    name2 = '/Users/davidparker/Documents/Flywheel/SSE/MyWork/Gears/Topup/Gear/work/orig_over_topup'
    outline_overlay(outline,background,name2)

    report_out = '/Users/davidparker/Documents/Flywheel/SSE/MyWork/Gears/Topup/Gear/work/report_out.png'
    plot_overlays([name1,name2], ['topup (red) over original','original (red) over topup'], report_out)



