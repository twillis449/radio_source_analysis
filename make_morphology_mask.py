#!/usr/bin/env python

import sys
import numpy as np
import subprocess
from astropy.io import fits
from check_array import check_array, update_dimensions
from astropy.io import fits
from astropy.wcs import WCS
from breizorro_extract import make_noise_map
from generate_morphology_image import make_morphology_image
from larrys_script import generate_morphology_images
from combine_images import combine_images
from process_polygon_data import *
import generate_mask_polygons as gen_p
import os

def make_mask(argv):
    """
    The parameters for doing morphological erosion
    filename: name of fits file  to process
    limiting_sigma: amount by which noise to to be multiplied for mask cutoff
    filter_size: size for structure element = radius of D or size of with for R
    filter_type: D = Disk, R = Rectangle

    The process can be described through the following equations:

    o = original image
    d - output from erosion-> erosion-> dilation
    t = white TopHat, which should show only compact structures smaller than the
        structure element
    t = o - d  
    m = mask derived from a comparison where  t > some signal
    m * t = m * (o - d)
    o_d = output diffuse image
        = o - m * t  
        = o - (m * o - m * d)
        = o - m * o + (m * d)

    we don't know the flux scale of m * d as we don't know the flux scale of the
    dilated image, but it is buried in the output image, so get rid of it
    by subtracting it off, which equates to

    o_d  = o - m * o
    and
    o_c = image of compact objects
        = m * o  

    """
    filename = argv[1] # fits file name without '.fits' extension
    limiting_sigma = argv[2]
    filter_size = argv[3] # integer number
    filter_type = argv[4] # 'D' or 'R'
    do_batch = argv[5]
    
    limiting_sigma = float(limiting_sigma)
    print('make_mask: incoming file name ', filename)
    print('make_mask: limiting_sigma ', limiting_sigma)
    print('make_mask: filter size', filter_size)
    print('make_mask: filter type', filter_type)
    print('make_mask: batch_processing', do_batch)
    if do_batch == 'T':
      do_batch = True
    else:
      do_batch = False

#   print('make_mask: processing original file', filename+'.fits')
    hdu_list = fits.open(filename+'.fits')
#   print ('info',hdu_list.info())
    hdu = hdu_list[0]
#   print('original image type =', hdu.data.dtype)
    incoming_dimensions = hdu.header['NAXIS']

    orig_image = check_array(hdu.data)
    nans = np.isnan(orig_image)
    orig_image[nans] = 0
#   print('original image  data max and min', hdu.data.max(), hdu.data.min())
# get noise from breizorro
    median_noise = make_noise_map(orig_image)
    print('make_mask: median noise ', median_noise)
    limiting_flux = median_noise * limiting_sigma
    print('make_mask: limiting_flux ', limiting_flux)
    # Download the morphology image
    # Load the image and the WCS
    print('calling make_morphology_image with size', filter_size)

#   o = original image
    morphology_image = make_morphology_image(filename, filter_size, filter_type)
#   d - output from erosion-> erosion-> dilation

#   print('morphology image data max and min', morphology_image.max(), morphology_image.min())


#   t = white TopHat, which should show only compact structures smaller than the
#       structure element
#   t = o - d  
    white_tophat = orig_image - morphology_image
    hdu.data = white_tophat
    hdu.header['DATAMIN'] = hdu.data.min()
    hdu.header['DATAMAX'] = hdu.data.max()
#   print('tophat image  data max and min', hdu.data.max(), hdu.data.min())
    out_tophat = filename +'-dilated_tophat.fits'
#   print('make_mask: tophat output to ', out_tophat )
    hdu.writeto(out_tophat, overwrite=True)

    
#   m = mask derived from a comparison where  t > some signal
# create mask from filtered image, where filtered image signal > limiting flux
    mask = np.where(white_tophat>limiting_flux,1.0,0.0)
    mask = mask.astype('float32')
    hdu.data = mask
    hdu.header['DATAMIN'] = 0.0
    hdu.header['DATAMAX'] = 1.0
    outfile = filename +'-dilated_tophat.mask.fits'
    print('mask output to ', outfile )
    hdu.writeto(outfile, overwrite=True)

# create filtered image from morphology image  * mask
# so we have filtered data which will be subtracted from original image
#   m * t = m * (o - d)
    filtered_data = white_tophat * mask
    filtered_morphology_image = morphology_image * mask
    nans = np.isnan(filtered_data)
    filtered_data[nans] = 0

#   print('filtered_data min and max', filtered_data.min(),  filtered_data.max())
    masked_diffuse_image = mask * morphology_image
    hdu.data = masked_diffuse_image
#   print('filtered data max and min', hdu.data.max(), hdu.data.min())
    hdu.header['DATAMAX'] =  filtered_data.max()
    hdu.header['DATAMIN'] =  filtered_data.min()

    outfile = filename +'.masked_diffuse_data.fits'
#   print('filtered_data image output to ', outfile )
#   write out m * d
    hdu.writeto(outfile, overwrite=True)

#   o_d = output diffuse image
#       = o - m * t  
#       = o - (m * o - m * d)
#       = o - m * o + (m * d)

#   we don't want m*d, but it is buried in the output image, so get rid of it
#   by subtracting it off, which equates to

#   m * o -> stuff with 'sharp' edges, o_c
    masked_image = orig_image *mask
#   print('compact image data max and min', hdu.data.max(), hdu.data.min())

    masked_image = update_dimensions(masked_image,incoming_dimensions)
    masked_image = masked_image.astype('float32')
    hdu.data = masked_image
    hdu.header['DATAMAX'] =  hdu.data.max()
    hdu.header['DATAMIN'] =  hdu.data.min()

#   print('hdu.data max and main', hdu.data.max(), hdu.data.min())
    compact_outfile = filename +'_compact_structure_dilated.fits'
#   print('********** final compact file', outfile)
    hdu.writeto(compact_outfile, overwrite=True)
#   print('wrote out', outfile)

#   o - m * o -> mostly diffuse features, o_d
    orig_image = update_dimensions(orig_image,incoming_dimensions)
    orig_image = orig_image.astype('float32')
    diffuse_image = orig_image - masked_image 
    hdu.data = diffuse_image
#   print('diffuse image data max and min', hdu.data.max(), hdu.data.min())
    hdu.header['DATAMAX'] =  hdu.data.max()
    hdu.header['DATAMIN'] =  hdu.data.min()

#   print('hdu.data max and main', hdu.data.max(), hdu.data.min())
    diffuse_outfile = filename +'_diffuse_structure_dilated.fits'
#   print('********** final diffuse', outfile)
    hdu.writeto(diffuse_outfile, overwrite=True)
#   print('wrote out', outfile)

# we may want to add some 'compact' features back into the diffuse image ...
# get locations of the features we want to add to the diffuse image 
# with the polygon selection tool - to obtaim mask m_c
    if not do_batch:
      polygon_gen = gen_p.make_polygon(hdu, mask, 'T')   # gives m_c
      polygons = polygon_gen.out_data
      coords = polygons['coords']
      if len(coords) > 0:
        print('calling combine_images')
        combine_images(filename, polygons, original_noise=median_noise)  # gives a modified image o* = o_d + m_c * o_c
        return

# otherewise, just link the diffuse file to final processed file
    fits_file_out = filename + '_final_image.fits'
    print('making a symbolic link')
    if os.path.isfile(fits_file_out):
      os.remove(fits_file_out)
    os.symlink(diffuse_outfile , fits_file_out)
    return

def main( argv ):
  """
   The parameters for doing morphological erosion:
   filename: argv[1] name of fits file  to process
   limiting_sigma: argv[2] amount by which noise to to be multiplied
                   for mask cutoff
   filter_size: argv[3] size for structure element 
              = radius of D or size of with for R
   filter_type: argv[4] D = Disk, R = Rectangle
   do_batch = argv[5] do batch processing? T = Yes, F = don't

  """
  if len(argv) > 4 :
# run AGW's code
    make_mask(argv)     # e.g. make_morphology_mask.py 3C236 6 5 D F
  else:
# otherwise run larry's code # eg make_orphology_mask.py XXX 5 5
# for the function call
# argv[1] = input file name
# argv[2] = X size of rectangle
# argv[3] = Y size of rectangle
    generate_morphology_images(argv)

if __name__ == '__main__':
    main(sys.argv)



