"""
bool specialization of AdjustedArrayWindow
"""
# cython: language_level=3

from numpy cimport uint8_t

ctypedef uint8_t[:, :] databuffer

include "_windowtemplate.pxi"
