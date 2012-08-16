cimport numpy as np
import numpy as np


cdef inline double bilinear_interpolation(double* image, int rows, int cols,
                                          double r, double c, char mode,
                                          double cval=*)

cdef inline double get_pixel(double* image, int rows, int cols, int r, int c,
                             char mode, double cval=*)

cdef inline int coord_map(int dim, int coord, char mode)