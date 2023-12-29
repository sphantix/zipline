"""
datetime specialization of AdjustedArrayWindow
"""
# cython: language_level=3

from numpy cimport int64_t

ctypedef int64_t[:, :] databuffer

include "_windowtemplate.pxi"
