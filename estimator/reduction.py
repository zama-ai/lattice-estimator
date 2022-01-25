# -*- coding: utf-8 -*-
"""
Cost estimates for lattice redution.
"""

from sage.all import ZZ, RR, pi, e, find_root, ceil, floor, log, oo, round, exp
from scipy.optimize import newton
from fpylll.util import gaussian_heuristic as gh


class ReductionCost:
    @staticmethod
    def _delta(beta):
        """
        Compute δ from block size β without enforcing β ∈ ZZ.

        δ for β ≤ 40 were computed as follows:

        ```
        # -*- coding: utf-8 -*-
        from fpylll import BKZ, IntegerMatrix

        from multiprocessing import Pool
        from sage.all import mean, sqrt, exp, log, cputime

        d, trials = 320, 32

        def f((A, beta)):

            par = BKZ.Param(block_size=beta, strategies=BKZ.DEFAULT_STRATEGY, flags=BKZ.AUTO_ABORT)
            q = A[-1, -1]
            d = A.nrows
            t = cputime()
            A = BKZ.reduction(A, par, float_type="dd")
            t = cputime(t)
            return t, exp(log(A[0].norm()/sqrt(q).n())/d)

        if __name__ == '__main__':
            for beta in (5, 10, 15, 20, 25, 28, 30, 35, 40):
                delta = []
                t = []
                i = 0
                  while i < trials:
                    threads = int(open("delta.nthreads").read()) # make sure this file exists
                    pool = Pool(threads)
                    A = [(IntegerMatrix.random(d, "qary", beta=d//2, bits=50), beta) for j in range(threads)]
                    for (t_, delta_) in pool.imap_unordered(f, A):
                        t.append(t_)
                        delta.append(delta_)
                    i += threads
                    print u"β: %2d, δ_0: %.5f, time: %5.1fs, (%2d,%2d)"%(beta, mean(delta), mean(t), i, threads)
                print
        ```

        """
        small = (
            (2, 1.02190),  # noqa
            (5, 1.01862),  # noqa
            (10, 1.01616),
            (15, 1.01485),
            (20, 1.01420),
            (25, 1.01342),
            (28, 1.01331),
            (40, 1.01295),
        )

        if beta <= 2:
            return RR(1.0219)
        elif beta < 40:
            for i in range(1, len(small)):
                if small[i][0] > beta:
                    return RR(small[i - 1][1])
        elif beta == 40:
            return RR(small[-1][1])
        else:
            return RR(beta / (2 * pi * e) * (pi * beta) ** (1 / beta)) ** (1 / (2 * (beta - 1)))

    @staticmethod
    def delta(beta):
        """
        Compute root-Hermite factor δ from block size β.

        :param beta: Block size.
        """
        beta = ZZ(round(beta))
        return ReductionCost._delta(beta)

    @staticmethod
    def _beta_secant(delta):
        """
        Estimate required block size β for a given root-Hermite factor δ based on [PhD:Chen13]_.

        :param delta: Root-Hermite factor.

        EXAMPLE::

            >>> from estimator.reduction import ReductionCost
            >>> ReductionCost._beta_secant(1.0121)
            50
            >>> ReductionCost._beta_secant(1.0093)
            100
            >>> ReductionCost._beta_secant(1.0024) # Chen reports 800
            808

        """
        # newton() will produce a "warning", if two subsequent function values are
        # indistinguishable (i.e. equal in terms of machine precision). In this case
        # newton() will return the value beta in the middle between the two values
        # k1,k2 for which the function values were indistinguishable.
        # Since f approaches zero for beta->+Infinity, this may be the case for very
        # large inputs, like beta=1e16.
        # For now, these warnings just get printed and the value beta is used anyways.
        # This seems reasonable, since for such large inputs the exact value of beta
        # doesn't make such a big difference.
        try:
            beta = newton(
                lambda beta: RR(ReductionCost._delta(beta) - delta),
                100,
                fprime=None,
                args=(),
                tol=1.48e-08,
                maxiter=500,
            )
            beta = ceil(beta)
            if beta < 40:
                # newton may output beta < 40. The old beta method wouldn't do this. For
                # consistency, call the old beta method, i.e. consider this try as "failed".
                raise RuntimeError("β < 40")
            return beta
        except (RuntimeError, TypeError):
            # if something fails, use old beta method
            beta = ReductionCost._beta_simple(delta)
            return beta

    @staticmethod
    def _beta_find_root(delta):
        """
        Estimate required block size β for a given root-Hermite factor δ based on [PhD:Chen13]_.

        :param delta: Root-Hermite factor.

        TESTS::

            >>> from estimator.reduction import ReductionCost, RC
            >>> ReductionCost._beta_find_root(RC.delta(500))
            500

        """
        # handle beta < 40 separately
        beta = ZZ(40)
        if ReductionCost._delta(beta) < delta:
            return beta

        try:
            beta = find_root(
                lambda beta: RR(ReductionCost._delta(beta) - delta), 40, 2 ** 16, maxiter=500
            )
            beta = ceil(beta - 1e-8)
        except RuntimeError:
            # finding root failed; reasons:
            # 1. maxiter not sufficient
            # 2. no root in given interval
            beta = ReductionCost._beta_simple(delta)
        return beta

    @staticmethod
    def _beta_simple(delta):
        """
        Estimate required block size β for a given root-Hermite factor δ based on [PhD:Chen13]_.

        :param delta: Root-Hermite factor.

        TESTS::

            >>> from estimator.reduction import ReductionCost, RC
            >>> ReductionCost._beta_simple(RC.delta(500))
            501

        """
        beta = ZZ(40)

        while ReductionCost._delta(2 * beta) > delta:
            beta *= 2
        while ReductionCost._delta(beta + 10) > delta:
            beta += 10
        while True:
            if ReductionCost._delta(beta) < delta:
                break
            beta += 1

        return beta

    def beta(delta):
        """
        Estimate required block size β for a given root-hermite factor δ based on [PhD:Chen13]_.

        :param delta: Root-hermite factor.

        EXAMPLE::

            >>> from estimator.reduction import RC
            >>> 50 == RC.beta(1.0121)
            True
            >>> 100 == RC.beta(1.0093)
            True
            >>> RC.beta(1.0024) # Chen reports 800
            808

        """
        # TODO: decide for one strategy (secant, find_root, old) and its error handling
        beta = ReductionCost._beta_find_root(delta)
        return beta

    @classmethod
    def svp_repeat(cls, beta, d):
        """
        Return number of SVP calls in BKZ-β.

        :param beta: Block size ≥ 2.
        :param d: Lattice dimension.

        .. note :: Loosely based on experiments in [PhD:Chen13].

        .. note :: When d ≤ β we return 1.

        """
        if beta < d:
            return 8 * d
        else:
            return 1

    @classmethod
    def LLL(cls, d, B=None):
        """
        Runtime estimation for LLL algorithm based on [AC:CheNgu11]_.

        :param d: Lattice dimension.
        :param B: Bit-size of entries.

        """
        if B:
            return d ** 3 * B ** 2
        else:
            return d ** 3  # ignoring B for backward compatibility

    def short_vectors(self, beta, d, N=None, B=None, preprocess=True):
        """
        Cost of outputting many somewhat short vectors.

        The output of this function is a tuple of three values:

        - `ρ` is a scaling factor. The output vectors are expected to be longer than the shortest
          vector expected from an SVP oracle by this factor.
        - `c` is the cost of outputting `N` vectors
        - `N` the number of vectors output, which may be larger than the value put in for `N`.

        This baseline implementation uses rerandomize+LLL as in [EC:Albrecht17]_.

        :param beta: Cost parameter (≈ SVP dimension).
        :param d: Lattice dimension.
        :param N: Number of vectors requested.
        :param B: Bit-size of entries.
        :param preprocess: Include the cost of preprocessing the basis with BKZ-β.
               If ``False`` we assume the basis is already BKZ-β reduced.
        :returns: ``(ρ, c, N)``

        EXAMPLES::

            >>> from estimator.reduction import RC
            >>> RC.CheNgu12.short_vectors(100, 500, N=1)
            (1.0, 1.67646...e17, 1)
            >>> RC.CheNgu12.short_vectors(100, 500, N=1, preprocess=False)
            (1.0, 1, 1)
            >>> RC.CheNgu12.short_vectors(100, 500)
            (2.0, 1.67646...e17, 1000)
            >>> RC.CheNgu12.short_vectors(100, 500, preprocess=False)
            (2.0, 125000000000, 1000)
            >>> RC.CheNgu12.short_vectors(100, 500, N=1000)
            (2.0, 1.67646...e17, 1000)
            >>> RC.CheNgu12.short_vectors(100, 500, N=1000, preprocess=False)
            (2.0, 125000000000, 1000)

        """

        if preprocess:
            cost = self(beta, d, B=B)
        else:
            cost = 0

        if N == 1:  # just call SVP
            return 1.0, cost + 1, 1
        elif N is None:
            N = 1000  # pick something

        return 2.0, cost + N * RC.LLL(d), N

    def short_vectors_simple(self, beta, d, N=None, B=None, preprocess=True):
        """
        Cost of outputting many somewhat short vectors.

        The output of this function is a tuple of three values:

        - `ρ` is a scaling factor. The output vectors are expected to be longer than the shortest
          vector expected from an SVP oracle by this factor.
        - `c` is the cost of outputting `N` vectors
        - `N` the number of vectors output, which may be larger than the value put in for `N`.

        This naive baseline implementation uses rerandomize+BKZ.

        :param beta: Cost parameter (≈ SVP dimension).
        :param d: Lattice dimension.
        :param N: Number of vectors requested.
        :param B: Bit-size of entries.
        :param preprocess: This option is ignore.
        :returns: ``(ρ, c, N)``

        EXAMPLES::

            >>> from estimator.reduction import RC
            >>> RC.CheNgu12.short_vectors_simple(100, 500, 1)
            (1.0, 1.67646160799173e17, 1)
            >>> RC.CheNgu12.short_vectors_simple(100, 500)
            (1.0, 1.67646160799173e20, 1000)
            >>> RC.CheNgu12.short_vectors_simple(100, 500, 1000)
            (1.0, 1.67646160799173e20, 1000)

        """
        if N == 1:
            if preprocess:
                return 1.0, self(beta, d, B=B), 1
            else:
                return 1.0, 1, 1
        elif N is None:
            N = 1000  # pick something
        return 1.0, N * self(beta, d, B=B), N

    def _short_vectors_sieve(self, beta, d, N=None, B=None, preprocess=True):
        """
        Cost of outputting many somewhat short vectors.

        The output of this function is a tuple of three values:

        - `ρ` is a scaling factor. The output vectors are expected to be longer than the shortest
          vector expected from an SVP oracle by this factor.
        - `c` is the cost of outputting `N` vectors
        - `N` the number of vectors output, which may be larger than the value put in for `N`.

        This implementation uses that a sieve outputs many somehwat short vectors [Kyber17]_.

        :param beta: Cost parameter (≈ SVP dimension).
        :param d: Lattice dimension.
        :param N: Number of vectors requested.
        :param B: Bit-size of entries.
        :param preprocess: Include the cost of preprocessing the basis with BKZ-β.
               If ``False`` we assume the basis is already BKZ-β reduced.
        :returns: ``(ρ, c, N)``

        EXAMPLES::

            >>> from estimator.reduction import RC
            >>> RC.ADPS16.short_vectors(100, 500, 1)
            (1.0, 6.16702733460158e8, 1)
            >>> RC.ADPS16.short_vectors(100, 500)
            (1.1547, 6.16702733460158e8, 1763487)
            >>> RC.ADPS16.short_vectors(100, 500, 1000)
            (1.1547, 6.16702733460158e8, 1763487)


        """
        if N == 1:
            if preprocess:
                return 1.0, self(beta, d, B=B), 1
            else:
                return 1.0, 1, 1
        elif N is None:
            N = floor(2 ** (0.2075 * beta))  # pick something

        c = N / floor(2 ** (0.2075 * beta))

        return 1.1547, ceil(c) * self(beta, d), ceil(c) * floor(2 ** (0.2075 * beta))


class BDGL16(ReductionCost):

    __name__ = "BDGL16"
    short_vectors = ReductionCost._short_vectors_sieve

    @classmethod
    def _small(cls, beta, d, B=None):
        """
        Runtime estimation given β and assuming sieving is used to realise the SVP oracle for small
        dimensions following [SODA:BDGL16]_.

        :param beta: Block size ≥ 2.
        :param d: Lattice dimension.
        :param B: Bit-size of entries.

        TESTS::

            >>> from math import log
            >>> from estimator.reduction import RC
            >>> log(RC.BDGL16._small(500, 1024), 2.0)
            222.9

        """
        return cls.LLL(d, B) + ZZ(2) ** RR(0.387 * beta + 16.4 + log(cls.svp_repeat(beta, d), 2))

    @classmethod
    def _asymptotic(cls, beta, d, B=None):
        """
        Runtime estimation given `β` and assuming sieving is used to realise the SVP oracle following [SODA:BDGL16]_.

        :param beta: Block size ≥ 2.
        :param d: Lattice dimension.
        :param B: Bit-size of entries.

        TESTS::

            >>> from math import log
            >>> from estimator.reduction import RC
            >>> log(RC.BDGL16._asymptotic(500, 1024), 2.0)
            175.4
        """
        # TODO we simply pick the same additive constant 16.4 as for the experimental result in [SODA:BDGL16]_
        return cls.LLL(d, B) + ZZ(2) ** RR(0.292 * beta + 16.4 + log(cls.svp_repeat(beta, d), 2))

    def __call__(self, beta, d, B=None):
        """
        Runtime estimation given `β` and assuming sieving is used to realise the SVP oracle following [SODA:BDGL16]_.

        :param beta: Block size ≥ 2.
        :param d: Lattice dimension.
        :param B: Bit-size of entries.

        EXAMPLE::

            >>> from math import log
            >>> from estimator.reduction import RC
            >>> log(RC.BDGL16(500, 1024), 2.0)
            175.4

        """
        # TODO this is somewhat arbitrary
        if beta <= 90:
            return self._small(beta, d, B)
        else:
            return self._asymptotic(beta, d, B)


class LaaMosPol14(ReductionCost):

    __name__ = "LaaMosPol14"
    short_vectors = ReductionCost._short_vectors_sieve

    def __call__(self, beta, d, B=None):
        """
        Runtime estimation for quantum sieving following [EPRINT:LaaMosPol14]_ and [PhD:Laarhoven15]_.

        :param beta: Block size ≥ 2.
        :param d: Lattice dimension.
        :param B: Bit-size of entries.

        EXAMPLE::

            >>> from math import log
            >>> from estimator.reduction import RC
            >>> log(RC.LaaMosPol14(500, 1024), 2.0)
            161.9

        """
        return self.LLL(d, B) + ZZ(2) ** RR(
            (0.265 * beta + 16.4 + log(self.svp_repeat(beta, d), 2))
        )


class CheNgu12(ReductionCost):

    __name__ = "CheNgu12"

    def __call__(self, beta, d, B=None):
        """
        Runtime estimation given β and assuming [CheNgu12]_ estimates are correct.

        :param beta: Block size ≥ 2.
        :param d: Lattice dimension.
        :param B: Bit-size of entries.

        The constants in this function were derived as follows based on Table 4 in
        [CheNgu12]_::

            >>> from sage.all import var, find_fit
            >>> dim = [100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200, 210, 220, 230, 240, 250]
            >>> nodes = [39.0, 44.0, 49.0, 54.0, 60.0, 66.0, 72.0, 78.0, 84.0, 96.0, 99.0, 105.0, 111.0, 120.0, 127.0, 134.0]  # noqa
            >>> times = [c + log(200,2).n() for c in nodes]
            >>> T = list(zip(dim, nodes))
            >>> var("a,b,c,beta")
            (a, b, c, beta)
            >>> f = a*beta*log(beta, 2.0) + b*beta + c
            >>> f = f.function(beta)
            >>> f.subs(find_fit(T, f, solution_dict=True))
            beta |--> 0.2701...*beta*log(beta) - 1.0192...*beta + 16.10...

        The estimation 2^(0.18728 β⋅log_2(β) - 1.019⋅β + 16.10) is of the number of enumeration
        nodes, hence we need to multiply by the number of cycles to process one node. This cost per
        node is typically estimated as 64.

        EXAMPLE::

            >>> from math import log
            >>> from estimator.reduction import RC
            >>> log(RC.CheNgu12(500, 1024), 2.0)
            365.70...

        """
        repeat = self.svp_repeat(beta, d)
        cost = RR(
            0.270188776350190 * beta * log(beta)
            - 1.0192050451318417 * beta
            + 16.10253135200765
            + log(100, 2)
        )
        return self.LLL(d, B) + repeat * ZZ(2) ** cost


class ABFKSW20(ReductionCost):

    __name__ = "ABFKSW20"

    def __call__(self, beta, d, B=None):
        """
        Enumeration cost according to [C:ABFKSW20]_.

        :param beta: Block size ≥ 2.
        :param d: Lattice dimension.
        :param B: Bit-size of entries.

        EXAMPLE::

            >>> from math import log
            >>> from estimator.reduction import RC
            >>> log(RC.ABFKSW20(500, 1024), 2.0)
            316.26...

        """
        if 1.5 * beta >= d or beta <= 92:  # 1.5β is a bit arbitrary, β≤92 is the crossover point
            cost = RR(0.1839 * beta * log(beta, 2) - 0.995 * beta + 16.25 + log(64, 2))
        else:
            cost = RR(0.125 * beta * log(beta, 2) - 0.547 * beta + 10.4 + log(64, 2))

        repeat = self.svp_repeat(beta, d)

        return self.LLL(d, B) + repeat * ZZ(2) ** cost


class ABLR21(ReductionCost):

    __name__ = "ABLR21"

    def __call__(self, beta, d, B=None):
        """
        Enumeration cost according to [C:ABLR21]_.

        :param beta: Block size ≥ 2.
        :param d: Lattice dimension.
        :param B: Bit-size of entries.

        EXAMPLE::

            >>> from math import log
            >>> from estimator.reduction import RC
            >>> log(RC.ABLR21(500, 1024), 2.0)
            278.20...

        """
        if 1.5 * beta >= d or beta <= 97:  # 1.5β is a bit arbitrary, 97 is the crossover
            cost = RR(0.1839 * beta * log(beta, 2) - 1.077 * beta + 29.12 + log(64, 2))
        else:
            cost = RR(0.1250 * beta * log(beta, 2) - 0.654 * beta + 25.84 + log(64, 2))

        repeat = self.svp_repeat(beta, d)

        return self.LLL(d, B) + repeat * ZZ(2) ** cost


class ADPS16(ReductionCost):

    __name__ = "ADPS16"
    short_vectors = ReductionCost._short_vectors_sieve

    def __call__(self, beta, d, B=None, mode="classical"):
        """
        Runtime estimation from [USENIX:ADPS16]_.

        :param beta: Block size ≥ 2.
        :param d: Lattice dimension.
        :param B: Bit-size of entries.

        EXAMPLE::

            >>> from math import log
            >>> from estimator.reduction import RC
            >>> log(RC.ADPS16(500, 1024), 2.0)
            146.0
            >>> log(RC.ADPS16(500, 1024, mode="quantum"), 2.0)
            132.5
            >>> log(RC.ADPS16(500, 1024, mode="paranoid"), 2.0)
            103.75

        """

        if mode not in ("classical", "quantum", "paranoid"):
            raise ValueError(f"Mode {mode} not understood.")

        c = {
            "classical": 0.2920,
            "quantum": 0.2650,  # paper writes 0.262 but this isn't right, see above
            "paranoid": 0.2075,
        }

        c = c[mode]

        return ZZ(2) ** RR(c * beta)


class Kyber(ReductionCost):

    __name__ = "Kyber"

    # These are not asymptotic expressions but compress the data in [AC:AGPS20]_ which covers up to
    # β = 1024
    NN_AGPS = {
        "all_pairs-classical": {"a": 0.4215069316613415, "b": 20.1669683097337},
        "all_pairs-dw": {"a": 0.3171724396445732, "b": 25.29828951733785},
        "all_pairs-g": {"a": 0.3155285835002801, "b": 22.478746811528048},
        "all_pairs-ge19": {"a": 0.3222895263943544, "b": 36.11746438609666},
        "all_pairs-naive_classical": {"a": 0.4186251294633655, "b": 9.899382654377058},
        "all_pairs-naive_quantum": {"a": 0.31401512556555794, "b": 7.694659515948326},
        "all_pairs-t_count": {"a": 0.31553282515234704, "b": 20.878594142502994},
        "list_decoding-classical": {"a": 0.2988026130564745, "b": 26.011121212891872},
        "list_decoding-dw": {"a": 0.26944796385592995, "b": 28.97237346443934},
        "list_decoding-g": {"a": 0.26937450988892553, "b": 26.925140365395972},
        "list_decoding-ge19": {"a": 0.2695210400018704, "b": 35.47132142280775},
        "list_decoding-naive_classical": {"a": 0.2973130399197453, "b": 21.142124058689426},
        "list_decoding-naive_quantum": {"a": 0.2674316807758961, "b": 18.720680589028465},
        "list_decoding-t_count": {"a": 0.26945736714156543, "b": 25.913746774011887},
        "random_buckets-classical": {"a": 0.35586144233444716, "b": 23.082527816636638},
        "random_buckets-dw": {"a": 0.30704199612690264, "b": 25.581968903639485},
        "random_buckets-g": {"a": 0.30610964725102385, "b": 22.928235564044563},
        "random_buckets-ge19": {"a": 0.31089687599538407, "b": 36.02129978813208},
        "random_buckets-naive_classical": {"a": 0.35448283789554513, "b": 15.28878540793908},
        "random_buckets-naive_quantum": {"a": 0.30211421791887644, "b": 11.151745013027089},
        "random_buckets-t_count": {"a": 0.30614770082829745, "b": 21.41830142853265},
    }

    @staticmethod
    def d4f(beta):
        """
        Dimensions "for free" following [EC:Ducas18]_.

        :param beta: Block size ≥ 2.

        If β' is output by this function then sieving is expected to be required up to dimension β-β'.

        EXAMPLE::

            >>> from estimator.reduction import RC
            >>> RC.Kyber.d4f(500)
            42.597...

        """
        return max(float(beta * log(4 / 3.0) / log(beta / (2 * pi * e))), 0.0)

    def __call__(self, beta, d, B=None, nn="classical", C=5.46):
        """
        Runtime estimation from [Kyber20]_ and [AC:AGPS20]_.

        :param beta: Block size ≥ 2.
        :param d: Lattice dimension.
        :param B: Bit-size of entries.
        :param nn: Nearest neighbor cost model. We default to "ListDecoding" (i.e. BDGL16) and to
                   the "depth × width" metric. Kyber uses "AllPairs".
        :param C: Progressive overhead lim_{β → ∞} ∑_{i ≤ β} 2^{0.292 i + o(i)}/2^{0.292 β + o(β)}.

        EXAMPLE::

            >>> from math import log
            >>> from estimator.reduction import RC
            >>> log(RC.Kyber(500, 1024), 2.0)
            176.61534319964488
            >>> log(RC.Kyber(500, 1024, nn="list_decoding-ge19"), 2.0)
            172.68208507350872

        """

        if beta < 20:  # goes haywire
            return CheNgu12()(beta, d, B)

        if nn == "classical":
            nn = "list_decoding-classical"
        elif nn == "quantum":
            nn = "list_decoding-dw"

        # "The cost of progressive BKZ with sieving up to blocksize b is essentially C · (n − b) ≈
        # 3340 times the cost of sieving for SVP in dimension b." [Kyber20]_
        svp_calls = C * max(d - beta, 1)
        # we do not round to the nearest integer to ensure cost is continuously increasing with β which
        # rounding can violate.
        beta_ = beta - self.d4f(beta)
        # "The work in [5] is motivated by the quantum/classical speed-up, therefore it does not
        # consider the required number of calls to AllPairSearch. Naive sieving requires a
        # polynomial number of calls to this routine, however this number of calls appears rather
        # small in practice using progressive sieving [40, 64], and we will assume that it needs to
        # be called only once per dimension during progressive sieving, for a cost of C · 2^137.4
        # gates^8." [Kyber20]_

        gate_count = C * 2 ** (RR(self.NN_AGPS[nn]["a"]) * beta_ + RR(self.NN_AGPS[nn]["b"]))
        return self.LLL(d, B=B) + svp_calls * gate_count

    def short_vectors(self, beta, d, N=None, B=None, preprocess=True):
        """
        Cost of outputting many somewhat short vectors using BKZ-β.

        The output of this function is a tuple of three values:

        - `ρ` is a scaling factor. The output vectors are expected to be longer than the shortest
          vector expected from an SVP oracle by this factor.
        - `c` is the cost of outputting `N` vectors
        - `N` the number of vectors output, which may be larger than the value put in for `N`.

        This is using an observation insprired by [AC:GuoJoh21]_ that we can run a sieve on the
        first block of the basis with negligible overhead.

        :param beta: Cost parameter (≈ SVP dimension).
        :param d: Lattice dimension.
        :param N: Number of vectors requested.
        :param preprocess: Include the cost of preprocessing the basis with BKZ-β.
               If ``False`` we assume the basis is already BKZ-β reduced.

        EXAMPLES::

            >>> from estimator.reduction import RC
            >>> RC.Kyber.short_vectors(100, 500, 1)
            (1.0, 2.73674761281368e19, 1)
            >>> RC.Kyber.short_vectors(100, 500)
            (1.1547, 2.73674761281368e19, 176584)
            >>> RC.Kyber.short_vectors(100, 500, 1000)
            (1.1547, 2.73674761281368e19, 176584)

        """
        beta_ = beta - floor(self.d4f(beta))

        if N == 1:
            if preprocess:
                return 1.0, self(beta, d, B=B), 1
            else:
                return 1.0, 1, 1
        elif N is None:
            N = floor(2 ** (0.2075 * beta_))  # pick something

        c = N / floor(2 ** (0.2075 * beta_))
        return 1.1547, ceil(c) * self(beta, d), ceil(c) * floor(2 ** (0.2075 * beta_))


class GJ21(Kyber):

    __name__ = "GJ21"

    def short_vectors(self, beta, d, N=None, preprocess=True, B=None, nn="classical", C=5.46):
        """
        Cost of outputting many somewhat short vectors according to [AC:GuoJoh21]_.

        The output of this function is a tuple of three values:

        - `ρ` is a scaling factor. The output vectors are expected to be longer than the shortest
          vector expected from an SVP oracle by this factor.
        - `c` is the cost of outputting `N` vectors
        - `N` the number of vectors output, which may be larger than the value put in for `N`.

        This runs a sieve on the first β_0 vectors of the basis after BKZ-β reduction
        to produce many short vectors, where β_0 is chosen such that BKZ-β reduction and the sieve
        run in approximately the same time. [AC:GuoJoh21]_

        :param beta: Cost parameter (≈ SVP dimension).
        :param d: Lattice dimension.
        :param N: Number of vectors requested.
        :param preprocess: Include the cost of preprocessing the basis with BKZ-β.
               If ``False`` we assume the basis is already BKZ-β reduced.
        :param B: Bit-size of entries.
        :param nn: Nearest neighbor cost model. We default to "ListDecoding" (i.e. BDGL16) and to
                   the "depth × width" metric. Kyber uses "AllPairs".
        :param C: Progressive overhead lim_{β → ∞} ∑_{i ≤ β} 2^{0.292 i + o(i)}/2^{0.292 β + o(β)}.

        EXAMPLES::

            >>> from estimator.reduction import RC
            >>> RC.GJ21.short_vectors(100, 500, 1)
            (1.0, 2.7367476128136...19, 1)
            >>> RC.GJ21.short_vectors(100, 500)
            (1.04794327225585, 5.56224438487945...19, 36150192)
            >>> RC.GJ21.short_vectors(100, 500, 1000)
            (1.04794327225585, 5.56224438487945...19, 36150192)

        """
        if nn == "classical":
            nn = "list_decoding-classical"
        elif nn == "quantum":
            nn = "list_decoding-dw"

        beta_ = beta - floor(self.d4f(beta))
        sieve_dim = beta_
        if beta < d:
            # set beta_sieve such that complexity of 1 sieve in in dim beta_sieve is approx
            # the same as the BKZ call
            sieve_dim = min(d, floor(beta_ + log((d - beta) * C, 2) / self.NN_AGPS[nn]["a"]))

        rho = 1.1547
        if sieve_dim > beta:
            # we assume the basis will be BKZ-β reduced
            log_delta = log(self.delta(beta), 2)
            # block of dimension beta_sieve has unit volume
            dummy_r = [1. for _ in range(sieve_dim)]
            beta_r = [exp(log_delta * (sieve_dim - 1 - 2 * i)) for i in range(beta)]
            rho *= RR(gh(dummy_r) / gh(beta_r))

        if N == 1:
            if preprocess:
                return 1.0, self(beta, d, B=B), 1
            else:
                return 1.0, 1, 1
        elif N is None:
            N = floor(2 ** (0.2075 * sieve_dim))  # pick something

        c = N / floor(2 ** (0.2075 * sieve_dim))
        sieve_cost = C * 2 ** (self.NN_AGPS[nn]["a"] * sieve_dim + self.NN_AGPS[nn]["b"])
        return rho, ceil(c) * (self(beta, d) + sieve_cost), ceil(c) * floor(2 ** (0.2075 * sieve_dim))


def cost(cost_model, beta, d, B=None, predicate=None, **kwds):
    """
    Return cost dictionary for computing vector of norm` δ_0^{d-1} Vol(Λ)^{1/d}` using provided lattice
    reduction algorithm.

    :param cost_model:
    :param beta: Block size ≥ 2.
    :param d: Lattice dimension.
    :param B: Bit-size of entries.
    :param predicate: if ``False`` cost will be infinity.

    EXAMPLE::

        >>> from estimator.reduction import cost, RC
        >>> cost(RC.ABLR21, 120, 500)
        rop: ≈2^68.9, red: ≈2^68.9, δ: 1.008435, β: 120, d: 500
        >>> cost(RC.ABLR21, 120, 500, predicate=False)
        rop: ≈2^inf, red: ≈2^inf, δ: 1.008435, β: 120, d: 500

    """
    from .cost import Cost

    # convenience: instantiate static classes if needed
    if isinstance(cost_model, type):
        cost_model = cost_model()

    cost = cost_model(beta, d, B)
    delta_ = ReductionCost.delta(beta)
    cost = Cost(rop=cost, red=cost, delta=delta_, beta=beta, d=d, **kwds)
    cost.register_impermanent(rop=True, red=True, delta=False, beta=False, d=False)
    if predicate is not None and not predicate:
        cost["red"] = oo
        cost["rop"] = oo
    return cost


beta = ReductionCost.beta  # noqa
delta = ReductionCost.delta  # noqa


class RC:
    beta = ReductionCost.beta
    delta = ReductionCost.delta

    LLL = ReductionCost.LLL
    ABFKSW20 = ABFKSW20()
    ABLR21 = ABLR21()
    ADPS16 = ADPS16()
    BDGL16 = BDGL16()
    CheNgu12 = CheNgu12()
    Kyber = Kyber()
    GJ21 = GJ21()
    LaaMosPol14 = LaaMosPol14()
