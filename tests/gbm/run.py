from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import warnings
import os.path
import numpy as np


def addExtraArguments(parser):
    parser.add_argument("-qoi_sigma", type=float, default=1.,
                        action="store", help="Volatility in GBM")
    parser.add_argument("-qoi_mu", type=float, default=1.,
                        action="store", help="Drift in GBM")
    parser.add_argument("-qoi_T", type=float, default=1.,
                        action="store", help="Final time in GBM")
    parser.add_argument("-qoi_S0", type=float, default=1.,
                        action="store", help="Initial condition in GBM")

try:
    # Try to import the DLL version of wcumsum,
    # This makes solving the SDE much faster
    import ctypes as ct
    import numpy.ctypeslib as npct
    __arr_double__ = npct.ndpointer(dtype=np.double, flags='C_CONTIGUOUS')
    __libdir = os.path.join(os.path.dirname(__file__))
    __lib__ = npct.load_library("libwcumsum.so", __libdir)
    __lib__.wcumsum.restype = None
    __lib__.wcumsum.argtypes = [__arr_double__, __arr_double__,
                                ct.c_uint32, __arr_double__]

    def wcumsum(x, w):
        output = np.empty(len(x))
        __lib__.wcumsum(x, w, len(x), output)
        return output

except:
    raise
    warnings.warn("Using Python (very slow) version for wcumsum. Consider running make")
    # wcumsum is like cumsum, but weighted.
    def wcumsum(x, w):
        output = np.empty(len(x))
        output[0] = x[0]
        for i in range(1, len(output)):
            output[i] = w[i]*output[i-1] + x[i]
        return output


def mySampleQoI(run, inds):
    meshes = (run.params.qoi_T/run.fnHierarchy(inds)).reshape(-1).astype(np.int)
    maxN = np.max(meshes)
    dW = np.random.normal(size=maxN)/np.sqrt(maxN)
    solves = np.empty(len(inds))
    for i, mesh in enumerate(meshes):
        # Simple Code to solve SDE!
        assert(maxN % mesh == 0)
        dWl = np.sum(dW.reshape((-1, maxN//mesh)), axis=1)
        solves[i] = wcumsum(np.concatenate(([run.params.qoi_S0],
                                            np.zeros(len(dWl)))),
                            np.concatenate(([0],
                                            run.params.qoi_sigma*dWl +
                                            1 + run.params.qoi_mu/mesh)))[-1]
    return solves

if __name__ == "__main__":
    import mimclib.test
    mimclib.test.RunStandardTest(fnSampleQoI=mySampleQoI,
                                 fnAddExtraArgs=addExtraArguments)
