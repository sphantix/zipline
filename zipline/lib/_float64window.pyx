"""
float specialization of AdjustedArrayWindow
"""
# cython: language_level=3

from numpy cimport float64_t
ctypedef float64_t[:, :] databuffer

include "_windowtemplate.pxi"
