#!/usr/bin/env python3

import os
import subprocess as sp
import logging
import matplotlib.pyplot as pl
import matplotlib.image as mpm

fsldir='/usr/lib/fsl/5.0'

def bet(image,workdir,shell=False):
    """
    Runs fsl's bet2 on an image and saves the results in workdir
    Args:
        image (str): path to the image to run bet2 on
        workdir (str): path for bet2 output (used to generate <output_fileroot> option in bet2
        shell (bool): pass the shell into the bet2 subprocess command
    Returns:
        bet_out (str): path to bet2's <output_fileroot> (currently "workdir"/bet
    """



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
    """
    Takes a bet2 extracted image and it's original, and creates a mask of the outline.  Requires that the "-o" option
    was used during bet2 to generate an overlay image.
    Args:
        original (str): path to the original image that bet2 was performed on
        bet_root (str): path to the bet2 root (the <output_fileroot> option used in bet2)
        shell (bool): use the shell in the subprocess commands

    Returns:
        bin_out (str): path to the binary bet2 outline mask.

    """

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



def overlay(image1,image2,output,shell=False):
    """
    creates an overlay of image 2 over image1.  Saves three .pngs of the overlay (one along each plane), and merges
    them into one single .png file
    Args:
        image1 (str): path to image1
        image2 (str): path to image2
        output (str): path to save merged overlays to
        shell (bool): include the shell in the subprocess commands or not

    Returns:

    """

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


def outline_overlay(background, outline, name=''):
    """
    Generates a .png image of one image's BET extracted brain outline over another image.  Each image containes three
    overlay views: one along each plane (Cor, Sag, Tra).
    Args:
        background (str): path to the backround image
        outline (str): path to the image who's BET extracted brain is outlined and overlayed on 'background'
        name (str): The name to save the final image as

    Returns:

    """


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

    bet_out = bet(outline, workdir, True)

    mask_outline = bet_2_outline(outline, bet_out, shell=False)
    overlay(background, mask_outline, name, shell=False)


def plot_overlays(files, titles, output):
    """
    Takes any number N of .png files, each with an associated title, and plots them together in a Nx1 subplot.
    Args:
        files (list): list of paths to .png images to include in the plot (ordered)
        titles (list): list of titles to assign to each plot
        output (str): the output name to save the image as

    Returns:

    """

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
    """
    Taking an original and topup corrected image, this creates a QA report image by overlaying an outline of the topup
    corrected image over the original, as well as overlaying an outline of the original image over the topup corrected
    image.  Three slices are taken from the center of the image, along each plane of acquistion (Sag, Cor, Tra)
    Args:
        original_image (str): path to original image
        corrected_image (str): path to TOPUP fixed image
        output_base (str): base directory for output files

    Returns:
        report_out (str): The path to the final QA image
    """

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



def debug():
    background = '/Users/davidparker/Documents/Flywheel/SSE/MyWork/Gears/Topup/Gear/work/Image1.nii.gz'
    outline = '/Users/davidparker/Documents/Flywheel/SSE/MyWork/Gears/Topup/Gear/output/topup_corrected_nodif.nii.gz'
    name1 = '/Users/davidparker/Documents/Flywheel/SSE/MyWork/Gears/Topup/Gear/work/topup_over_orig'
    outline_overlay(background, outline, name1)

    name2 = '/Users/davidparker/Documents/Flywheel/SSE/MyWork/Gears/Topup/Gear/work/orig_over_topup'
    outline_overlay(outline,background,name2)

    report_out = '/Users/davidparker/Documents/Flywheel/SSE/MyWork/Gears/Topup/Gear/work/report_out.png'
    plot_overlays([name1,name2], ['topup (red) over original','original (red) over topup'], report_out)


if __name__ == '__main__':
    debug()




