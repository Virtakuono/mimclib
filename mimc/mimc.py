from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import itertools
import warnings
import set_util

class MIMCData(object):
    def __init__(self, dim, lvls=None,
                 psums=None, t=None, M=None):
        self.dim = dim
        self.lvls = lvls          # MIMC lvls
        self.psums = psums        # sums of lvls
        self.t = t                # Time of lvls
        self.M = M                # Number of samples in each lvl
        if self.lvls is None:
            self.lvls = []
        if self.psums is None:
            self.psums = np.empty((0, 2))
        if self.t is None:
            self.t = np.empty(0)
        if self.M is None:
            self.M = np.empty(0, dtype=np.int)

    def calcEg(self):
        return np.sum(self.calcEl())

    def __len__(self):
        return len(self.lvls)

    def __getitem__(self, ind):
        return MIMCData(self.dim,
                        lvls=np.array(self.lvls, dtype=object)[ind].tolist(),
                        psums=self.psums[ind, :], t=self.t[ind],
                        M=self.M[ind])

    def Dim(self):
        return self.dim

    def calcVl(self):
        return self.psums[:, 1] / self.M - (self.calcEl())**2

    def calcEl(self, moment=1):
        assert(moment > 0)
        return self.psums[:, moment-1] / self.M

    def calcTl(self):
        return self.t / self.M

    def calcTotalTime(self, ind=None):
        return np.sum(self.t)

    def addSamples(self, psums, M, t):
        assert psums.shape[0] == len(M) and len(M) == len(t), \
            "Inconsistent arguments "

        self.psums += psums
        self.M += M
        self.t += t

    def zero_samples(self):
        self.M = np.zeros_like(self.M)
        self.t = np.zeros_like(self.t)
        self.psums = np.zeros_like(self.psums)

    def addLevels(self, new_lvls):
        assert(len(new_lvls) > 0)
        prev = len(self.lvls)
        self.lvls.extend(new_lvls)
        s = len(self.lvls)
        self.psums.resize((s, self.psums.shape[1]), refcheck=False)
        self.t.resize(s, refcheck=False)
        self.M.resize(s, refcheck=False)
        return prev


class MyDefaultDict(object):
    def __init__(self, **kwargs):
        self.__dict__ = dict([i for i in kwargs.items() if i[1] is not None])
        self.__defaults__ = dict()
        self.__warn_defaults__ = dict()

    def set_defaults(self, **kwargs):
        self.__defaults__ = kwargs

    def set_warn_defaults(self, **kwargs):
        self.__warn_defaults__ = kwargs

    def __getattr__(self, name):
        if name in self.__defaults__:
            return self.__defaults__[name]
        if name in self.__warn_defaults__:
            default_val = self.__warn_defaults__[name]
            warnings.warn("Argument '{}' is required but not provided,\
default value '{}' is used.".format(name, default_val))
            return default_val
        raise NameError("Argument '{}' is required but not \
provided!".format(name))


class MIMCRun(object):
    def __init__(self, **kwargs):
        self.params = MyDefaultDict(**kwargs)
        # self.params.set_defaults(bayesian=False, abs_bnd=False,
        #                          reuse_samples=True,
        #                          const_theta=False)
        # self.params.set_warn_defaults(Ca=3, theta=0.5,
        #                               fnWorkModel=lambda x: x.Tl())

        self.bias = np.inf           # Approximation of the discretization error
        self.stat_error = np.inf     # Sampling error (based on M)

        self.data = MIMCData(dim=self.params.dim)
        self.all_data = MIMCData(dim=self.params.dim)
        # If self.params.reuse_samples is True then
        # all_data will always equal data
        if self.params.bayesian and 'fnWorkModel' not in kwargs:
            raise NotImplementedError("Bayesian parameter fitting is only \
supported with a given work model")

        if self.params.bayesian and 'fnHierarchy' not in kwargs:
            raise NotImplementedError("Bayesian parameter fitting is only \
supported with a given hierarchy")

        if self.params.bayesian and self.data.dim > 1:
            raise NotImplementedError("Bayesian parameter fitting is only \
supported in one dimensional problem")

        if self.params.bayesian:
            self.Q = MyDefaultDict(S=0, W=0, w=self.params.w,
                                   s=self.params.s)
        if 'fnWorkModel' not in kwargs:
            # ADDING WORK MODEL B
            warnings.warn("fnWorkModel is not provided, using run-time estimates.")
            self.params.fnWorkModel = lambda x: x.Tl()

    @staticmethod
    def addOptionsToParser(parser, pre='-mimc_', additional=True):
        def str2bool(v):
            # susendberg's function
            return v.lower() in ("yes", "true", "t", "1")
        mimcgrp = parser.add_argument_group('MIMC', 'Arguments to control MIMC logic')
        mimcgrp.register('type', 'bool', str2bool)

        def add_store(name, **kwargs):
            if "default" in kwargs and "help" in kwargs:
                kwargs["help"] += " (default: {})".format(kwargs["default"])
            mimcgrp.add_argument(pre + name, dest=name,
                                 action="store",
                                 **kwargs)

        add_store('verbose', type='bool', default=False,
                  help="Verbose output")
        add_store('bayesian', type='bool', default=False,
                  help="Use Bayesian fitting to estimate bias, variance and optimize number\
of levels every iteration. This is based on CMLMC.")
        add_store('dim', type=int, help="Number of dimensions used in MIMC")
        add_store('reuse_samples', type='bool', default=True,
                  help="Reuse samples between iterations")
        add_store('abs_bnd', type='bool', default=False,
                  help="Take absolute value of deltas when \
estimating bias (sometimes that's too conservative).")
        add_store('const_theta', type='bool', default=False,
                  help="Use the same theta for all iterations")
        add_store('Ca', type=float, default=3,
                  help="Parameter to control confidence level")
        add_store('theta', type=float, default=0.5,
                  help="Default theta or error splitting parameter.")
        add_store('incL', type=int, default=2,
                  help="Maximum increment of number of levels \
between iterations")
        add_store('w', nargs='+', type=float,
                  help="Weak convergence rates. Must be of size -DIM")
        add_store('s', nargs='+', type=float,
                  help="Strong convergence rates. Must be of size -DIM")
        add_store('kappa0', type=float, default=0.1,
                  help="Variance in prior of the constant \
in the weak convergence model")
        add_store('kappa1', type=float, default=0.1,
                  help="Variance in prior of the constant \
in the strong convergence model")
        add_store('w_sig', type=float, default=-1,
                  help="Variance in prior of the power \
in the weak convergence model, negative values lead to disabling the fitting")
        add_store('s_sig', type=float, default=-1,
                  help="Variance in prior of the power \
in the weak convergence model, negative values lead to disabling the fitting")

        if additional:
            add_store('TOL', type=float,
                      help="The required tolerance for the MIMC run")
            add_store('maxTOL', type=float, default=0.1,
                      help="The (approximate) tolerance for \
the first iteration.")
            add_store('M0', type=int, default=10, help="The initial number of samples \
used to estimate the sample variance when not using the Bayesian estimators")
            add_store('min_lvls', type=int, default=2,
                      help="The initial number of levels to run \
the first iteration")
            add_store('max_add_itr', type=int, default=2,
                      help="Maximum number of additonal iterations\
to run when the MIMC is expected to but is not converging")
            add_store('r1', type=float, default=2,
                      help="A parameters to control to tolerance sequence \
for tolerance larger than TOL")
            add_store('r2', type=float, default=1.1,
                      help="A parameters to control to tolerance sequence \
for tolerance smaller than TOL")
            add_store('beta', type=float, default=2,
                      help="Level separation parameter to be used \
with get_geometric_hl")
            add_store('h0', type=float, default=2,
                      help="Minimum element size get_geometric_hl")
            add_store('gamma', type=float,
                      help="Work exponent to be used with work_estimate")
        return mimcgrp

    def calcTotalWork(self):
        return np.sum(self.fnWorkModel(self, self.data.lvls) * self.data.M)

    def estimateStatError(self):
        return self.params.Ca * \
            np.sqrt(np.sum(self._estimateVl() / self.data.M))

    def estimateTotalError(self):
        return self.estimateBias() + self.estimateStateError()

    def __str__(self):
        output = "Time={:.12e}\nEg={:.12e}\n\
Bias={:.12e}\nstatErr={:.12e}\n".format(self.data.calcTotalTime(),
                                       self.data.calcEg(),
                                       self.bias,
                                       self.stat_error)
        V = self._estimateVl()
        E = self.data.calcEl()
        T = self.data.calcTl()

        output += ("{:<8}{:^20}{:^20}{:>8}{:>15}{:>8}\n".format(
            "Level", "E", "V", "M", "Time", "Var%"))
        for i in range(0, len(self.data.lvls)):
            output += ("{:<8}{:>+20.12e}{:>20.12e}{:>8}{:>15.6e}{:>8.2f}%\n".format(
                self.data.lvls[i], E[i], V[i], self.data.M[i], T[i],
                100 * np.sqrt(V[i]) / np.abs(E[i])))
        return output

    def _estimateVl(self):
        if not self.params.bayesian:
            return self.data.calcVl()
        return self._estimateBaysianVl()

    ################## Bayesian specific functions
    def estimateBias(self):
        if not self.params.bayesian:
            bnd = is_boundary(self.data.dim, self.data.lvls)
            if np.sum(bnd) == len(self.data.lvls):
                return np.inf
            bnd_val = self.data[bnd].calcEl()
            if self.params.abs_bnd:
                return np.abs(np.sum(np.abs(bnd_val)))
            return np.abs(np.sum(bnd_val))
        return self._estimateBayesianBias()

    def _estimateBayesianBias(self, L=None):
        L = L or len(self.all_data.lvls)-1
        if L <= 1:
            raise Exception("Must have at least 2 levels")
        hl = self.params.fnHierarchy(self, np.arange(0, L+1).reshape((-1, 1)))
        return np.abs(self.Q.W) * hl[-1]**self.Q.w[0]

    def _estimateBayesianVl(self, L=None):
        L = L or len(self.all_data.lvls)-1
        if L <= 1:
            raise Exception("Must have at least 2 levels")
        hl = self.params.fnHierarchy(self, np.arange(0,L+1).reshape((-1,1)))
        M = self.all_data[1:].M
        m1 = self.all_data[1:].calcEl()
        m2 = self.all_data[1:].calcEl(moment=2)
        mu = self.Q.W*(hl[1:]**self.Q.w[0] - hl[:-1]**self.Q.w[0])
        Lambda = 1./(self.Q.S*(hl[1:]**(self.Q.s[0]/2.) - hl[:-1]**(self.Q.s[0]/2.))**2)
        G_3 = self.params.kappa1 * Lambda + M
        G_4 = self.params.kappa1 + \
              0.5*M*(m2-m1**2 + self.params.kappa0 * (m1 - mu)**2 /
                     (self.params.kappa0 + M))
        allVl = np.concatenate(self.data[0].calcVl(), G_4 / G_3)
        if len(allVl) >= L+1:
            return allVl[:L+1]
        return np.concatenate(allVl, np.zeros(L+1-len(AllVl)))

    def _estimateParams(self):
        if not self.params.bayesian:
            return
        L = len(self.all_data.lvls)-1
        if L <= 1:
            raise Exception("Must have at least 2 levels")
        hl = self.params.fnHierarchy(self, np.arange(0, L+1).reshape((-1, 1)))
        begin = 1
        M = self.all_data[begin:].M
        m1 = self.all_data[begin:].calcEl()
        m2 = self.all_data[begin:].calcEl(moment=2)
        wl = hl[begin:]**self.Q.w[0] - hl[(begin-1):-1]**self.Q.w[0]
        sl = (hl[begin:]**(self.Q.s[0]/2.) - hl[(begin-1):-1]**(self.Q.s[0]/2.))**-2
        self.Q.W = np.sum(wl * sl * M * m1) / np.sum(M * wl**2 * sl)
        self.Q.S = np.sum(sl * (m2 - 2*m1*self.Q.W*wl + self.Q.W**2*wl**2)) / np.sum(M)
        if self.params.w_sig > 0 or self.params.s_sig > 0:
            # TODO: Estimate w=q_1, s=q_2
            raise NotImplemented("TODO, estimate w and s")

    def _estimateOptimalL(self, TOL):
        assert self.params.bayesian, "MIMC should be Bayesian to \
estimate optimal number of levels"
        minL = len(self.data)
        minWork = np.inf
        for L in range(len(self.data.lvls), len(self.data.lvls)+1+self.params.incL):
            Wl = self.params.fnWorkModel(self,
                                         np.arange(0, L+1).reshape((-1, 1)))
            M, _ = self._calcTheoryM(TOL,
                                     bias_est=self._estimateBayesianBias(L),
                                     Vl=self._estimateBayesianVl(L), Wl=Wl)
            totalWork = np.sum(Wl*M)
            if totalWork < minWork:
                minL = L
                minWork = totalWork
        return minL
    ################## END: Bayesian specific function

    def _addLevels(self, lvls):
        self.data.addLevels(lvls)
        self.all_data.addLevels(lvls)

    def _calcSamples(self, fnSamplelvl, totalM, verbose):
        lvls = self.data.lvls
        s = len(lvls)
        M = np.zeros(s, dtype=np.int)
        psums = np.zeros((s, 2))
        p = np.arange(1, psums.shape[1])
        t = np.zeros(s)
        for i in range(0, s):
            if totalM[i] <= self.data[i].M:
                continue
            if verbose:
                print("# Doing", totalM[i]-self.data[i].M, "of level", lvls[i])
            mods, inds = lvl_to_inds_general(lvls[i])
            psums[i, :], t[i] = fnSamplelvl(self, p, mods, inds,
                                            totalM[i] - self.data[i].M)
            M[i] = totalM[i]
        self.data.addSamples(psums, M, t)
        self.all_data.addSamples(psums, M, t)

    def _calcTheoryM(self, TOL, bias_est, Vl, Wl):
        theta = -1
        if not self.params.const_theta:
            theta = 1 - bias_est/TOL
        if theta <= 0:
            theta = self.params.theta   # Bias too large or const_theta
        return (theta * TOL / self.params.Ca)**-2 *\
            np.sum(np.sqrt(Wl * Vl)) * np.sqrt(Vl / Wl), theta

    def doRun(self, fnSampleLvls, finalTOL=None, fnExtendLvls=None,
              TOLs=None, fnItrDone=None, verbose=None):
        # fnExtendLvls(MIMCRun): Returns new lvls and number of samples on each.
        #                        called only once if the Bayesian method is used
        # fnSampleLvls(MIMCRun, moments, mods, inds, M):
        #    Returns array: M sums of mods*inds, and total (linear) time it took to compute them
        # fnItrDone(MIMCRun, i, TOLs): Called at the end of iteration i out of TOLs
        # fnWorkModel(MIMCRun, lvls): Returns work estimate of lvls
        # fnHierarchy(MIMCRun, lvls): Returns associated hierarchy of lvls
        finalTOL = finalTOL or self.params.TOL
        TOLs = TOLs or get_tol_sequence(finalTOL, self.params.maxTOL,
                                        max_additional_itr=self.params.max_add_itr,
                                        r1=self.params.r1,
                                        r2=self.params.r2)
        fnExtendLvls = fnExtendLvls or (lambda r:
                                        extend_lvls_tensor(r,
                                                           r.params.M0,
                                                           r.params.min_lvls))
        if verbose is None:
            verbose = self.params.verbose

        if len(self.data.lvls) != 0:
            warnings.warn("Running the same object twice, resetting")
            self.data = MIMCData(self.data.dim)
        if not all(x >= y for x, y in zip(TOLs, TOLs[1:])):
            raise Exception("Tolerances must be decreasing")

        import time
        tic = time.time()
        newLvls, todoM = fnExtendLvls(self)
        self._addLevels(newLvls)
        self._calcSamples(fnSampleLvls, todoM, verbose)

        import gc
        for itrIndex, TOL in enumerate(TOLs):
            if verbose:
                print("# TOL", TOL)
            while True:
                gc.collect()
                self._estimateParams()
                if self.params.bayesian:
                    L = self._estimateOptimalL(TOL)
                    if L > len(self.data.lvls):
                        self.data._addLevels(np.arange(len(self.data.lvls),
                                                       L+1).reshape((-1, 1)))
                todoM, theta = self._calcTheoryM(TOL,
                                                 self.estimateBias(),
                                                 self._estimateVl(),
                                                 self.params.fnWorkModel(self,
                                                                         self.data.lvls))
                todoM = todoM.astype(np.int)
                if verbose:
                    print("# theta", theta)
                    print("# New M: ", todoM)
                if not self.params.reuse_samples:
                    self.data.zero_samples()
                self._calcSamples(fnSampleLvls, todoM, verbose)
                self.stat_error = self.estimateStatError()
                self.bias = self.estimateBias()
                self.totalTime = time.time() - tic
                if verbose:
                    print(self)
                    print("------------------------------------------------")
                if self.params.bayesian or (self.bias + self.stat_error < TOL):
                    if verbose:
                        print("{} took {}".format(TOL, self.totalTime))
                    break
                if self.bias > (1 - theta) * TOL:
                    # Bias is not satisfied. Add more levels
                    newlvls, newTodoM = fnExtendLvls(self)
                    prev = len(self.data.lvls)
                    self._addLevels(newlvls)
                    self._calcSamples(fnSampleLvls,
                                      np.concatenate((self.data.M[:prev],
                                                      newTodoM)), verbose)
            if fnItrDone:
                fnItrDone(self, itrIndex, TOL)
            if TOL <= finalTOL:
                break


def extend_lvls_tensor(run, M0, min_lvls=2):
    d, lvls = run.data.dim, run.data.lvls
    if len(lvls) <= 0:
        newlvls = [[0] * d]
        # TODO: should add multiple levels
        #count = min_lvls+1
    else:
        deg = np.max([np.max(ll) for ll in lvls])
        newlvls = list()
        additions = [f for f in itertools.product([0, 1], repeat=d) if max(f) > 0]
        for l in [ll for ll in lvls if np.max(ll) == deg]:
            newlvls.extend([(np.array(l) + a).tolist() for a in
                            additions if np.max(np.array(l) + a) ==
                            deg + 1 and (np.array(l) + a).tolist() not
                            in newlvls])
    return newlvls, M0*np.ones(len(newlvls), dtype=np.int)


def extend_lvls_td(run, w):
    lvls = run.data.lvls
    prev_deg = np.max(np.sum(np.array(
        [w*np.array(l) for l in lvls]), axis=1)) if lvls else 0
    max_deg = prev_deg
    while True:
        max_deg += np.min(w)
        C, _ = set_util.AnisoProfCalculator(w*0, w).GetIndexSet(max_deg)
        all_lvls = C.to_dense_matrix() - 1
        newlvls = [lvl.tolist() for lvl in all_lvls if lvl.tolist() not in lvls]
        if len(newlvls) > 0:
            return newlvls


def work_estimate(lvls, gamma):
    return np.prod(np.exp(np.array(lvls)*gamma), axis=1)


def is_boundary(d, lvls):
    if len(lvls) == 1:
        return [True]   # Special case for zero element
    bnd = np.zeros(len(lvls), dtype=int)
    for i in range(0, d):
        x = np.zeros(d)
        x[i] = 1
        bnd += np.array([1 if l[i] == 0 or (np.array(l)+x).tolist() in lvls else 0 for l in lvls])
    return bnd < d


def lvl_to_inds_general(lvl):
    lvl = np.array(lvl, dtype=np.int)
    seeds = list()
    for i in range(0, lvl.shape[0]):
        if lvl[i] == 0:
            seeds.append([0])
        else:
            seeds.append([0, 1])
    inds = np.array(list(itertools.product(*seeds)), dtype=np.int)
    mods = (2 * np.sum(lvl) % 2 - 1) * (2 * (np.sum(inds, axis=1) % 2) - 1)
    return mods, np.tile(lvl, (inds.shape[0], 1)) - inds


def get_geometric_hl(lvls, h0, beta):
    return h0*beta**(np.array(lvls, dtype=np.uint32))


def get_tol_sequence(TOL, maxTOL, max_additional_itr=1, r1=2, r2=1.1):
    # number of iterations until TOL
    eni = int(-(np.log(TOL)-np.log(maxTOL))/np.log(r1))
    return np.concatenate((TOL*r1**np.arange(eni, -1, -1),
                           TOL*r2**-np.arange(1, max_additional_itr+1)))


def get_optimal_hl(mimc):
    if mimc.data.dim != 1:
        raise NotImplemented("Optimized hierarchies are only supported\
 for one-dimensional problems")

    # TODO: Get formula from HajiAli 2015, Optimizing MLMC hierarchies
    raise NotImplemented("TODO: get_optimal_hl")
