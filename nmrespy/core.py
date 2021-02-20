from copy import deepcopy
import datetime
import functools
import inspect
import itertools
import json
import os
from pathlib import Path
import pickle
import re
import shutil
import sys

import matplotlib
import matplotlib.pyplot as plt

import numpy as np

from scipy.integrate import simps

from nmrespy import *
import nmrespy._cols as cols
if cols.USE_COLORAMA:
    import colorama
import nmrespy._errors as errors
from nmrespy._misc import *
from nmrespy.load import load_bruker
from nmrespy.filter import FrequencyFilter
from nmrespy.mpm import MatrixPencil
from nmrespy.nlp.nlp import NonlinearProgramming
from nmrespy.write import write_result
from nmrespy import signal


class Estimator:
    """Estimation class

    .. note::
       The methods :py:meth:`new_bruker`, :py:meth:`new_synthetic_from_data`
       and :py:meth:`new_synthetic_from_parameters` generate instances
       of the class. The method :py:meth:`from_pickle` loads an estimator
       instance that was previously saved using :py:meth:`to_pickle`.
       While you can manually input the listed parameters
       as arguments to initialise the class, it is more straightforward
       to use one of these.

    Parameters
    ----------
    source : 'bruker_fid', 'bruker_pdata', 'synthetic'
        The type of data imported. `'bruker_fid'` indicates the data is
        derived from a FID file (`fid` for 1D data, `ser` for 2D data).
        `'bruker_pdata'` indicates the data is derived from files found
        in a `pdata` directory (`1r` for 1D data; `2rr` for 2D data).
        `'synthetic'` indicates that the data is synthetic.

    data : numpy.ndarray
        The data associated with the binary file in `path`.

    path : pathlib.Path or None
        The path to the directory contaioning the NMR data.

    sw : [float] or [float, float]
        The experiment sweep width in each dimension (Hz).

    off : [float] or [float, float]
        The transmitter's offset frequency in each dimension (Hz).

    sfo : [float] or [float, float] or None
        The transmitter frequency in each dimension (MHz)

    nuc : [str] or [str, str] or None
        The nucleus in each dimension. Elements will be of the form
        `'<mass><element>'`, where `'<mass>'` is the mass number of the
        isotope and `'<element>'` is the chemical symbol of the element.

    fmt : str or None
        The format of the binary file from which the data was obtained.
        Of the form `'<endian><unitsize>'`, where `'<endian>'` is either
        `'<'` (little endian) or `'>'` (big endian), and `'<unitsize>'`
        is either `'i4'` (32-bit integer) or `'f8'` (64-bit float).

    _origin : dict or None, default None
        For internal use. Specifies how the instance was initalised. If `None`,
        implies that the instance was initialised manually, rather than using
        one of :py:meth:`new_bruker`, :py:meth:`new_synthetic_from_data`
        and :py:meth:`new_synthetic_from_parameters`.
    """

    def new_bruker(dir, ask_convdta=True):
        """Generate an instance of :py:class:`Estimator` from a
        Bruker-formatted data directory.

        Parameters
        ----------
        dir : str
            The path to the data containing the data of interest.

        ask_convdta : bool
            See :py:meth:`nmrespy.load_bruker`

        Returns
        -------
        estimator : :py:meth:`nmrespy.core.Estimator`

        Notes
        -----
        For a more detailed specification of the directory requirements,
        see :py:meth:`nmrespy.load_bruker`

        Example
        -------
        .. code:: python3

           >>> from nmrespy.core import Estimator
           >>> path = "/opt/topspin4.0.8/examdata/exam1d_1H/1/pdata/1"
           >>> estimator = Estimator.new_bruker(path)
           >>> print(estimator)
           <nmrespy.core.Estimator at 0x7ff2821deb80>
           source : bruker_pdata
           data : [ 8.23724176e+06+0.00000000e+00j  9.17136243e+05-4.97070634e+06j
            -3.95415395e+06+6.85640849e+05j ...  4.70675320e+00-8.16149817e+01j
            -4.41587513e+01-9.79437505e+00j  5.74582742e+00+5.69385271e+01j]
           dim : 1
           n : [16384]
           path : /opt/topspin4.0.8/examdata/exam1d_1H/1/pdata/1
           sw : [5494.50549450549]
           off : [2249.20599998768]
           sfo : [500.132249206]
           nuc : ['1H']
           fmt : <i4
           filter_info : None
           mpm_info : None
           nlp_info : None
           _converter : <nmrespy._misc.FrequencyConverter object at 0x7ff282250910>
           _logpath : /home/.../python3.8/site-packages/nmrespy/logs/210212183053.log
        """
        origin={'method':'new_bruker', 'args':locals()}
        info = load_bruker(dir, ask_convdta=ask_convdta)

        return Estimator(
            info['source'], info['data'], info['directory'],
            info['sweep_width'], info['offset'], info['transmitter_frequency'],
            info['nuclei'], info['binary_format'], _origin=origin
        )

    def new_synthetic_from_data(data, sw, offset=None, sfo=None):
        """Generate an instance of :py:class:`Estimator` given a NumPy
        array, and (at the bare minimum), the sweep width.

        Parameters
        ----------
        data : numpy.ndarray
            Time-domain signal.

        sw : [float] or [float, float]
            Sweep width in each dimension (Hz).

        offset: [float], [float, float] or None, default: None
            TranSmitter offset in each dimension (Hz). By default, the offset
            is set to zero in each dimension.

        sfo : [float], [float, float] or None, default: None
            The transmitter frequency in each dimension (MHz). Used to
            convert frequencies to ppm. If `None`, conversion to ppm will
            not be possible.

        Returns
        -------
        estimator : :py:meth:`nmrespy.core.Estimator`

        Example
        -------
        .. code:: python3

           >>> import numpy as np
           >>> from nmrespy.core import Estimator
           >>> from nmrespy.signal import make_fid
           >>> parameters = np.array([
           ...     [1, 0, 3, 0.2],
           ...     [2, 0, 1, 0.15],
           ...     [3, 0, -2, 0.2],
           ... ])
           >>> sw = [10.0]
           >>> offset = [0.0]
           >>> n = [2048]
           >>> fid, _ = make_fid(parameters, n, sw)
           >>> estimator = Estimator.new_synthetic_from_data(fid, sw)
           >>> print(estimator)
           <nmrespy.core.Estimator at 0x7fc926998e20>
           source : synthetic
           data : [ 6.00000000e+00+0.00000000e+00j  2.19679226e+00-7.06717824e-01j
           -2.51152989e+00-4.11235694e-01j ... -7.59762676e-14-5.51367204e-14j
           -2.86058106e-14-8.79414766e-14j  2.81452206e-14-8.66344585e-14j]
           dim : 1
           n : [2048]
           path : None
           sw : [10.0]
           off : [0.0]
           sfo : None
           nuc : None
           fmt : None
           filter_info : None
           mpm_info : None
           nlp_info : None
           _logpath : /home/.../python3.8/site-packages/nmrespy/logs/210212184026.log
        """

        # --- Check validity of parameters -------------------------------
        # Check data is a numpy array
        if not isinstance(data, np.ndarray):
            raise TypeError(
                f'{cols.R}data should be a numpy ndarray{cols.END}'
            )
        # Determine data dimension. If greater than 2, return error.
        if data.ndim >= 3:
            raise errors.MoreThanTwoDimError()

        dim = data.ndim

        # If offset is None, set it to zero in each dimension
        if offset == None:
            offset = [0.0] * dim

        components = [
            (sw, 'sw', 'float_list'),
            (offset, 'offset', 'float_list'),
        ]

        if sfo != None:
            components.append((sfo, 'sfo', 'float_list'))

        ArgumentChecker(components, dim)

        return Estimator(
            'synthetic', data, None, sw, offset, sfo, None, None,
        )


    def new_synthetic_from_parameters(
        parameters, sw, points, snr=None, offset=None, sfo=None
    ):
        """
        .. todo::
           THis has not been written yet.
        """
        print(f'{cols.O}new_synthetic_from_parameters is not yet'
              f'implemented!{cols.END}')


    def from_pickle(path):
        """Loads an intance of :py:class:`Estimator`, which was saved
        previously using :py:meth:`to_pickle`.

        Parameters
        ----------
        path : str
            The path to the pickle file. DO NOT INCLUDE THE FILE
            EXTENSION.

        Returns
        -------
        estimator : :py:meth:`nmrespy.core.Estimator`

        Notes
        -----
        .. warning::
           `From the Python docs:`

           *"The pickle module is not secure. Only unpickle data you trust.
           It is possible to construct malicious pickle data which will
           execute arbitrary code during unpickling. Never unpickle data
           that could have come from an untrusted source, or that could have
           been tampered with."*

           You should only use :py:meth:`from_pickle` on files that
           you are 100% certain were generated using
           :py:meth:`to_pickle`. If you load pickled data from a .pkl file,
           and the resulting output is not an instance of
           :py:class:`Estimator`, an error will be raised.
        """

        path = Path(path).with_suffix('.pkl')
        if path.is_file():
            with open(path, 'rb') as fh:
                obj = pickle.load(fh)
            if isinstance(obj, __class__):
                return obj
            else:
                raise TypeError(
                    f'{cols.R}It is expected that the object opened by'
                    ' from_pickle is an instance of'
                    f' {__class__.__module__}.{__class__.__qualname__}.'
                    f' What was loaded didn\'t satisfy this!{cols.END}'
                )

        else:
            raise ValueError(
                f'{cols.R}Invalid path specified.{cols.END}'
            )


    def to_pickle(
        self, path='./nmrespy_instance', force_overwrite=False
    ):
        """Converts the class instance to a byte stream using Python's
        "Pickling" protocol, and saves it to a .pkl file.

        Parameters
        ----------
        path : str, default: './nmrespy_instance'
            Path of file to save the byte stream to. DO NOT INCLUDE A
            `'.pkl'` EXTENSION! `'.pkl'` is added to the end of the path
            automatically.

        force_overwrite : bool, default: False
            Defines behaviour if ``f'{path}.pkl'`` already exists:

            * If `force_overwrite` is set to `False`, the user will be prompted
              if they are happy overwriting the current file.
            * If `force_overwrite` is set to `True`, the current file will be
              overwritten without prompt.

        Notes
        -----
        This method complements :py:meth:`from_pickle`, in that
        an instance saved using :py:meth:`to_pickle` can be recovered by
        :py:func:`~nmrespy.load.pickle_load`.
        """

        ArgumentChecker(
            [
                (path, 'path', 'str'),
                (force_overwrite, 'force_overwrite', 'bool'),
            ]
        )

        # Get full path
        path = Path(path).resolve()
        # Append extension to file path
        path = path.parent / (path.name + '.pkl')
        # Check path is valid (check directory exists, ask user if they are happy
        # overwriting if file already exists).
        pathres = PathManager(path.name, path.parent).check_file(force_overwrite)
        # Valid path, we are good to proceed
        if pathres == 0:
            pass
        # Overwrite denied by the user. Exit the program
        elif pathres == 1:
            exit()
        # pathres == 2: Directory specified doesn't exist
        else:
            raise ValueError(
                f'{cols.R}The directory implied by path does not exist{cols.END}'
            )

        with open(path, 'wb') as fh:
            pickle.dump(self, fh, pickle.HIGHEST_PROTOCOL)

        print(f'{cols.G}Saved instance of Estimator to {path}{cols.END}')


    def __init__(
        self, source, data, path, sw, off, sfo, nuc, fmt, _origin=None
    ):
        self.source = source
        self.data = data
        self.dim = self.data.ndim
        self.n = [int(n) for n in self.data.shape]
        self.path = path
        self.sw = sw
        self.off = off
        self.sfo = sfo
        self.nuc = nuc
        self.fmt = fmt

        # Attributes that will be assigned to after the user runs
        # the folowing methods:
        # 1. frequency_filter (filter_info)
        # 2. matrix_pencil (mpm_info)
        # 3. nonlinear_programming (nlp_info)
        self.filter_info = None
        self.mpm_info = None
        self.nlp_info = None
        # Create a converter object, enabling conversion idx, hz (and ppm,
        # if sfo is not None)
        self._converter = FrequencyConverter(
            list(data.shape), self.sw, self.off, self.sfo
        )

        # --- Create file for logging method calls -----------------------
        # Set path of file to be inside the nmrespy/logs directory
        # File name is a timestamp: yyyymmddHHMMSS.log
        now = datetime.datetime.now()
        self._logpath = Path(NMRESPYPATH) / \
                       f"logs/{now.strftime('%y%m%d%H%M%S')}.log"

        # Add a header to the log file
        header = (
            '==============================\n'
            'Logfile for Estimator instance\n'
            '==============================\n'
           f"--> Instance created @ {now.strftime('%d-%m-%y %H:%M:%S')}"
        )

        if _origin is not None:
            header += f" from {_origin['method']} with args {_origin['args']}"

        header += '\n'

        with open(self._logpath, 'w') as fh:
            fh.write(header)


    def __repr__(self):
        msg = (
            f'nmrespy.core.Estimator('
            f'{self.source}, '
            f'{self.data}, '
            f'{self.path}, '
            f'{self.sw}, '
            f'{self.off}, '
            f'{self.n}, '
            f'{self.sfo}, '
            f'{self.nuc}, '
            f'{self.fmt})'
        )

        return msg


    def __str__(self):
        """A formatted list of class attributes"""

        msg = (
            f"{cols.MA}<{__class__.__module__}.{__class__.__qualname__} at "
            f"{hex(id(self))}>{cols.END}\n"
        )

        dic = self.__dict__
        keys, vals = dic.keys(), dic.values()
        items = [f'{cols.MA}{k}{cols.END} : {v}' for k, v in zip(keys, vals)]
        msg += '\n'.join(items)

        return msg


    def logger(f):
        """Decorator for logging :py:class:`Estimator` method calls"""
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            # The first arg is the class instance. Get the path to the logfile.
            path = args[0]._logpath
            with open(path, 'a') as fh:
                # Append the method call to the log file in the following format:
                # --> method_name (args) {kwargs}
                fh.write(f'--> {f.__name__} {args[1:]} {kwargs}\n')

            # Run the method...
            return f(*args, **kwargs)

        return wrapper


    def get_datapath(self, type_='Path', kill=True):
        """Return path of the data directory.

        Parameters
        ----------
        type_ : 'Path' or 'str', default: 'Path'
            The type of the returned path. If `'Path'`, the returned object
            is an instance of `pathlib.Path <https://docs.python.org/3/\
            library/pathlib.html#pathlib.Path>`_. If `'str'`, the returned
            object is an instance of str.

        kill : bool, default: True
            If the path is `None`, `kill` specifies how the method will act:

            * If `True`, an AttributeIsNoneError is raised.
            * If `False`, `None` is returned.

        Returns
        -------
        path : str or pathlib.Path
        """

        path = self._check_if_none('path', kill)

        if type_ == 'Path':
            return path
        elif type_ == 'str':
            return str(path) if path is not None else None
        else:
            raise ValueError(f'{R}type_ should be \'Path\' or \'str\'')


    def get_data(self):
        """Return the original data.

        Returns
        -------
        data : numpy.ndarray
        """
        return self.data


    def get_dim(self):
        """Return the data dimension.

        Returns
        -------
        dim : 1 or 2
        """
        return self.dim


    def get_n(self):
        """Return the number of datapoints in each dimension

        Returns
        -------
        n : [int] or [int, int]
        """
        return self.n


    def get_sw(self, unit='hz'):
        """Return the experiment sweep width in each dimension.

        Parameters
        ----------
        unit : 'hz' or 'ppm', default: 'hz'

        Returns
        -------
        sw : [float] or [float, float]

        Raises
        ------
        InvalidUnitError
            If `unit` is not `'hz'` or `'ppm'`

        Notes
        -----
        If `unit` is set to `'ppm'` and `self.sfo` is not specified
        (`None`), there is no way of retreiving the sweep width in ppm.
        `None` will be returned.
        """

        if unit == 'hz':
            return self.sw
        elif unit == 'ppm':
            try:
                return self._converter.convert(self.sw, 'hz->ppm')
            except:
                return None
        else:
            raise errors.InvalidUnitError('hz', 'ppm')


    def get_offset(self, unit='hz'):
        """Return the transmitter's offset frequency in each dimesnion.

        Parameters
        ----------
        unit : 'hz' or 'ppm', default: 'hz'

        Returns
        -------
        offset : [float] or [float, float]

        Raises
        ------
        InvalidUnitError
            If `unit` is not `'hz'` or `'ppm'`

        Notes
        -----
        If `unit` is set to `'ppm'` and `self.sfo` is not specified
        (`None`), there is no way of retreiving the offset in ppm.
        `None` will be returned.
        """

        if unit == 'hz':
            return self.off
        elif unit == 'ppm':
            try:
                return self._converter.convert(self.off, 'hz->ppm')
            except:
                return None
        else:
            raise errors.InvalidUnitError('hz', 'ppm')

    def get_sfo(self, kill=True):
        """Return transmitter frequency for each channel (MHz).

        Parameters
        ----------
        kill : bool, default: True
            If the path is `None`, `kill` specifies how the method will act:

            * If `True`, an AttributeIsNoneError is raised.
            * If `False`, `None` is returned.

        Returns
        -------
        sfo : [float] or [float, float]
        """

        return self._check_if_none('sfo', kill)

    def get_bf(self, kill=True):
        """Return the transmitter's basic frequency for each channel (MHz).

        Parameters
        ----------
        kill : bool, default: True
            If the path is `None`, `kill` specifies how the method will act:

            * If `True`, an AttributeIsNoneError is raised.
            * If `False`, `None` is returned.

        Returns
        -------
        bf : [float] or [float, float]
        """

        sfo = self._check_if_none('sfo', kill)
        if sfo == None:
            return None

        off = self.get_offset()
        return [s - (o / 1E6) for s, o in zip(sfo, off)]

    def get_nucleus(self, kill=True):
        """Return the target nucleus of each channel.

        Parameters
        ----------
        kill : bool, default: True
            If the path is `None`, `kill` specifies how the method will act:

            * If `True`, an AttributeIsNoneError is raised.
            * If `False`, `None` is returned.

        Returns
        -------
        nuc : [str] or [str, str]
        """

        return self._check_if_none('nuc', kill)

    def get_shifts(self, unit='hz', meshgrid=False, kill=True):
        """Return the sampled frequencies consistent with experiment's
        parameters (sweep width, transmitter offset, number of points).

        Parameters
        ----------
        unit : 'ppm' or 'hz', default: 'ppm'
            The unit of the value(s).

        meshgrid : bool
            Only appicable for 2D data. If set to `True`, the shifts in
            each dimension will be fed into `numpy.meshgrid <https://numpy.org/\
            doc/stable/reference/generated/numpy.meshgrid.html>`_

        kill : bool
            If `self.sfo` (need to get shifts in ppm) is `None`, `kill`
            specifies how the method will act:

            * If `True`, an AttributeIsNoneError is raised.
            * If `False`, `None` is returned.

        Returns
        -------
        shifts : [numpy.ndarray] or [numpy.ndarray, numpy.ndarray]
            The frequencies sampled along each dimension.

        Raises
        ------
        InvalidUnitError
            If `unit` is not `'hz'` or `'ppm'`

        Notes
        -----
        The shifts are returned in ascending order.
        """

        if unit not in ['ppm', 'hz']:
            raise errors.InvalidUnitError('ppm', 'hz')

        shifts = signal.get_shifts(
            self.get_n(), self.get_sw(), self.get_offset()
        )

        if unit == 'ppm':
            sfo = self.get_sfo(kill)
            if sfo == None:
                return None
            shifts = [shifts_ / sfo for shifts_ in shifts]

        if self.get_dim() == 2 and meshgrid:
            return list(np.meshgrid(shifts[0], shifts[1]))

        return shifts


    def get_timepoints(self, meshgrid=False):
        """Return the sampled times consistent with experiment's
        parameters (sweep width, number of points).

        Parameters
        ----------
        meshgrid : bool
            Only appicable for 2D data. If set to `True`, the time-points in
            each dimension will be fed into `numpy.meshgrid <https://numpy.org/\
            doc/stable/reference/generated/numpy.meshgrid.html>`_

        Returns
        -------
        tp : [numpy.ndarray] or [numpy.ndarray, numpy.ndarray]
            The times sampled along each dimension (seconds).
        """

        tp = signal.get_timepoints(self.get_n(), self.get_sw())
        if meshgrid and self.get_dim() == 2:
            return list(np.meshgrid(tp[0], tp[1]))
        return tp

    def _check_if_none(self, name, kill, method=None):
        """Retrieve attributes that may be assigned the value `None`. Return
        None/raise error depending on the value of ``kill``

        Parameters
        ----------
        name : str
            The name of the attribute requested.

        kill : bool
            Whether or not to raise an error if the desired attribute is
            `None`.

        method : str or None, default: None
            The name of the method that needs to be run to obtain the
            desired attribute. If `None`, it implies that the attribute
            requested was never given to the class in the first place.

        Returns
        -------
        attribute : any
            The attribute requested.
        """

        attribute = self.__dict__[name]
        if attribute is None:
            if kill is True:
                raise errors.AttributeIsNoneError(name, method)
            else:
                return None

        else:
            return attribute


    def view_data(self, domain='frequency', freq_xunit='ppm', component='real'):
        """Generate a simple, interactive plot of the data using matplotlib.

        Parameters
        ----------
        domain : 'frequency' or 'time', default: 'frequency'
            The domain of the signal.

        freq_xunit : 'ppm' or 'hz', default: 'ppm'
            The unit of the x-axis, if `domain` is set as `'frequency'`. If
            `domain` is set as `'time'`, the x-axis unit will the seconds.
        """
        # TODO: 2D equivalent
        dim = self.get_dim()

        if domain == 'time':
            if dim == 1:
                xlabel = '$t\\ (s)$'
                ydata = self.get_data()
                xdata = self.get_tp()[0]

            elif dim == 2:
                raise errors.TwoDimUnsupportedError()

        elif domain == 'frequency':
            # frequency domain treatment
            if dim == 1:
                ydata = fftshift(fft(self.get_data()))

                if freq_xunit == 'hz':
                    xlabel = '$\\omega\\ (Hz)$'
                    xdata = self.get_shifts(unit='hz')[0]
                elif freq_xunit == 'ppm':
                    xlabel = '$\\omega\\ (ppm)$'
                    xdata = self.get_shifts(unit='ppm')[0]
                else:
                    msg = f'{R}freq_xunit was not given a valid value' \
                          + f' (should be \'ppm\' or \'hz\').{END}'
                    raise ValueError(msg)

            elif dim == 2:
                raise errors.TwoDimUnsupportedError()

        else:
            msg = f'{R}domain was not given a valid value' \
                  + f' (should be \'frequency\' or \'time\').{END}'
            raise ValueError(msg)

        if component == 'real':
            plt.plot(xdata, np.real(ydata), color='k')
        elif component == 'imag':
            plt.plot(xdata, np.imag(ydata), color='k')
        elif component == 'both':
            plt.plot(xdata, np.real(ydata), color='k')
            plt.plot(xdata, np.imag(ydata), color='#808080')
        else:
            msg = f'{R}component was not given a valid value' \
                  + f' (should be \'real\', \'imag\' or \'both\').{END}'
            raise ValueError(msg)

        if domain == 'frequency':
            plt.xlim(xdata[-1], xdata[0])
        plt.xlabel(xlabel)
        plt.show()

# TODO
# make_fid:
# include functionality to write to Bruker files, Varian files,
# JEOL files etc
# =============================================================

    def make_fid(self, n=None, oscillators=None):
        """Constructs a synthetic FID using a parameter estimate and
        experiment parameters.

        Parameters
        ----------
        n : [int], or [int, int], or None default: None
            The number of points to construct the FID with in each dimesnion.
            If `None`, :py:meth:`get_n` will be used, meaning the signal will
            have the same number of points as the original data.

        oscillators : None or list, default: None
            Which oscillators to include in result. If ``None``, all
            oscillators will be included. If a list of ints, the subset of
            oscillators corresponding to these indices will be used. Note
            that the valid list elements are the ints from `0` to
            ``self.nlp_info.result.shape[0] - 1`` (included).

        Returns
        -------
        fid : numpy.ndarray
            The generated FID.

        tp : [numpy.ndarray] or [numpy.ndarray, numpy.ndarray]
            The time-points at which the signal is sampled, in each dimension.

        See Also
        --------
        :py:func:`nmrespy.signal.make_fid`
        """

        result = self.get_nlp_info(kill=False).get_result()
        if result is None:
            raise ValueError(
                f'{cols.R}No parameter estimate found! Perhaps you need to'
                f' run nonlinear_programming?{cols.END}'
            )

        if oscillators:
            # slice desired oscillators
            result = result[[oscillators]]

        if n is None:
            n = self.get_n()
        ArgumentChecker([(n, 'n', 'int_list')], dim=self.get_dim())


        return signal.make_fid(
            result, n, self.get_sw(), offset=self.get_offset(),
        )

    @logger
    def phase_data(self, p0=None, p1=None):
        """Phase `self.data`

        Parameters
        ----------
        p0 : [float], [float, float], or None default: None
            Zero-order phase correction in each dimension in radians.
            If `None`, the phase will be set to `0.0` in each dimension.

        p1 : [float], [float, float], or None default: None
            First-order phase correction in each dimension in radians.
            If `None`, the phase will be set to `0.0` in each dimension.
        """

        self.p0 = p0
        self.p1 = p1

        if self.p0 is None:
            self.p0 = self.get_dim() * [0.0]
        if self.p1 is None:
            self.p1 = self.get_dim() * [0.0]

        self.data = signal.ift(
            signal.phase_spectrum(
                signal.ft(self.data), self.p0, self.p1,
            )
        )

    def manual_phase_data(self, max_p1=None):
        """Perform manual phase correction of `self.data`.

        Zero- and first-order phase pharameters are determined via
        interaction with a Tkinter- and matplotlib-based graphical user
        interface.

        Parameters
        ----------
        max_p1 : float or None, default: None
            Specifies the range of first-order phases permitted. For each
            dimension, the user will be allowed to choose a value of `p1`
            within [`-max_p1`, `max_p1`]. By default, `max_p1` will be
            ``10 * numpy.pi``.
        """
        p0, p1 = signal.manual_phase_spectrum(signal.ft(self.data), max_p1=None)
        self.phase_data(p0=p0, p1=p1)

    @logger
    def frequency_filter(
        self, region, noise_region, cut=True, cut_ratio=3.0, region_unit='ppm',
    ):
        """Generates frequency-filtered data from `self.data`
        supplied.

        Parameters
        ----------
        region: [[int, int]], [[int, int], [int, int]], [[float, float]] or [[float, float], [float, float]]
            Cut-off points of the spectral region to consider.
            If the signal is 1D, this should be of the form `[[a,b]]`
            where `a` and `b` are the boundaries.
            If the signal is 2D, this should be of the form
            `[[a,b], [c,d]]` where `a` and `b` are the boundaries in
            dimension 1, and `c` and `d` are the boundaries in
            dimension 2. The ordering of the bounds in each dimension is
            not important.

        noise_region: [[int, int]], [[int, int], [int, int]], [[float, float]] or [[float, float], [float, float]]
            Cut-off points of the spectral region to extract the spectrum's
            noise variance. This should have the same structure as `region`.

        cut : bool, default: True
            If `False`, the filtered signal will comprise the same number of
            data points as the original data. If `True`, prior to inverse
            FT, the data will be sliced, with points not in the region
            specified by `cut_ratio` being removed.

        cut_ratio : float, default: 2.5
            If cut is `True`, defines the ratio between the cut signal's sweep
            width, and the region width, in each dimesnion.
            It is reccommended that this is comfortably larger than `1.0`.
            `2.0` or higher should be appropriate.

        region_unit : 'ppm', 'hz' or 'idx', default: 'ppm'
            The unit the elements of `region` and `noise_region` are
            expressed in.

        Notes
        -----
        This method assigns the attribute `filter_info` to an instance of
        :py:class:`nmrespy.filter.FrequencyFilter`. To obtain information
        on the filtration, use :py:meth:`get_filter_info`.
        """

        self.filter_info = FrequencyFilter(
            self.get_data(), region, noise_region, region_unit=region_unit,
            sw=self.get_sw(), offset=self.get_offset(),
            sfo=self.get_sfo(kill=False), cut=cut,
            cut_ratio=cut_ratio,
        )

    def get_filter_info(self, kill=True):
        """Returns information relating to frequency filtration.

        Parameters
        ----------
        kill : bool, default: True
            If `filter_info` is `None`, and `kill` is `True`, an error will
            be raised. If `kill` is False, `None` will be returned.

        Returns
        -------
        filter_info : nmrespy.filter.FrequencyFilter

        Notes
        -----
        There are numerous methods associated with `filter_info` for
        obtaining relavent infomation about the filtration. See
        :py:class:`nmrespy.filter.FrequencyFilter` for details.
        """

        return self._check_if_none(
            'filter_info', kill, method='frequency_filter'
        )

    def _get_data_sw_offset(self):
        """Retrieve data, sweep width and offset, based on whether
        frequency filtration have been applied.

        Returns
        -------
        data : numpy.ndarray

        sw : [float] or [float, float]
            Sweep width (Hz).

        offset : [float] or [float, float]
            Transmitter offset (Hz).

        Notes
        -----
        * If `self.filter_info` is equal to `None`, `self.data` will be
          analysed
        * If `self.filter_info` is an instance of
          :py:class:`nmrespy.filter.FrequencyFilter`,
          `self.filter_info.filtered_signal` will be analysed.
        """
        filter_info = self.filter_info

        if filter_info == None:
            data = self.data
            sw = self.sw
            offset = self.offset

        elif isinstance(filter_info, FrequencyFilter):
            data = filter_info.filtered_signal
            sw = filter_info.sw
            offset = filter_info.offset

        return data, sw, offset

    @logger
    def matrix_pencil(self, M=0, trim=None, fprint=True):
        """Implementation of the 1D Matrix Pencil Method [#]_ [#]_ or 2D
        Modified Matrix Enchancement and Matrix Pencil (MMEMP) method [#]_
        [#]_ with the option of Model Order Selection using the Minumum
        Descrition Length (MDL) [#]_.

        Parameters
        ----------
        M : int, default: 0
            The number of oscillators to use in generating a parameter
            estimate. If `M` is set to `0`, the number of oscillators will be
            estimated using the MDL.

        trim : [int], [int, int], or None, default: None
            If `trim` is a list, the analysed data will be sliced such that
            its shape matches `trim`, with the initial points in the signal
            being retained. If `trim` is `None`, the data will not be
            sliced. Consider using this in cases where the full signal is
            large, such that the method takes a very long time, or your PC
            has insufficient memory to process it.

        fprint : bool, default: True
            If `True` (default), the method provides information on
            progress to the terminal as it runs. If `False`, the method
            will run silently.

        Notes
        -----
        The data analysed will be the following:

        * If `self.filter_info` is equal to `None`, `self.data` will be
          analysed
        * If `self.filter_info` is an instance of
          :py:class:`nmrespy.filter.FrequencyFilter`,
          `self.filter_info.filtered_signal` will be analysed.

        **For developers:** See :py:meth:`_get_data_sw_offset`

        Upon successful completion is this method, `self.mpm_info` will
        be updated with an instance of :py:class:`nmrespy.mpm.MatrixPencil`.

        References
        ----------
        .. [#] Yingbo Hua and Tapan K Sarkar. “Matrix pencil method for
           estimating parameters of exponentially damped/undamped sinusoids
           in noise”. In: IEEE Trans. Acoust., Speech, Signal Process. 38.5
           (1990), pp. 814–824.

        .. [#] Yung-Ya Lin et al. “A novel detection–estimation scheme for
           noisy NMR signals: applications to delayed acquisition data”.
           In: J. Magn. Reson. 128.1 (1997), pp. 30–41.

        .. [#] Yingbo Hua. “Estimating two-dimensional frequencies by matrix
           enhancement and matrix pencil”. In: [Proceedings] ICASSP 91: 1991
           International Conference on Acoustics, Speech, and Signal
           Processing. IEEE. 1991, pp. 3073–3076.

        .. [#] Fang-Jiong Chen et al. “Estimation of two-dimensional
           frequencies using modified matrix pencil method”. In: IEEE Trans.
           Signal Process. 55.2 (2007), pp. 718–724.

        .. [#] M. Wax, T. Kailath, Detection of signals by information theoretic
           criteria, IEEE Transactions on Acoustics, Speech, and Signal Processing
           33 (2) (1985) 387–392.
        """

        data, sw, offset = self._get_data_sw_offset()

        if trim is None:
            trim = [s for s in data.shape]

        ArgumentChecker([(trim, 'trim', 'int_list')], dim=self.dim)

        trim = tuple(np.s_[0:t] for t in trim)
        # Slice data
        data = data[trim]

        self.mpm_info = MatrixPencil(
            data, sw, offset, self.sfo, M, fprint
        )

    def get_mpm_info(self, kill=True):
        """Returns information relating to the Matrix Pencil Method.

        Parameters
        ----------
        kill : bool, default: True
            If `self.mpm_info` is `None`, and `kill` is `True`, an error will
            be raised. If `kill` is False, `None` will be returned.

        Returns
        -------
        mpm_info : :py:class:`nmrespy.filter.MatrixPencil`

        Notes
        -----
        See :py:class:`nmrespy.mpm.MatrixPencil` for details on the contents
        of `mpm_info`.
        """

        return self._check_if_none(
            'mpm_info', kill, method='matrix_pencil'
        )

    @logger
    def nonlinear_programming(self, trim=None, **kwargs):
        """Estimation of signal parameters using nonlinear programming, given
        an inital guess.

        Parameters
        ----------
        trim : None, [int], or [int, int], default: None
            If `trim` is a list, the analysed data will be sliced such that
            its shape matches `trim`, with the initial points in the signal
            being retained. If `trim` is `None`, the data will not be
            sliced. Consider using this in cases where the full signal is
            large, such that the method takes a very long time, or your PC
            has insufficient memory to process it.

        **kwargs
            Properties of :py:class:`nmrespy.nlp.nlp.NonlinearProgramming`.

            Valid arguments:

            * `phase_variance`
            * `method`
            * `mode`
            * `bound`
            * `max_iterations`
            * `amp_thold`
            * `freq_thold`
            * `negative_amps`
            * `fprint`

        Raises
        ------
        PhaseVarianceAmbiguityError
            Raised when ``phase_variance`` is set to ``True``, but the user
            has specified that they do not wish to optimise phases using the
            ``mode`` argument.

        Notes
        -----
        The data analysed will be the following:

        * If `self.filter_info` is equal to `None`, `self.data` will be
          analysed
        * If `self.filter_info` is an instance of
          :py:class:`nmrespy.filter.FrequencyFilter`,
          `self.filter_info.filtered_signal` will be analysed.

        **For developers:** See :py:meth:`_get_data_sw_offset`

        Upon successful completion is this method, `self.nlp_info` will
        be updated with an instance of
        :py:class:`nmrespy.nlp.nlp.NonlinearProgramming`.

        The two optimisation algorithms (specified by `method`) primarily
        differ in how they treat the calculation of the matrix of cost
        function second derivatives (called the Hessian). `'trust_region'`
        will calculate the Hessian explicitly at every iteration, whilst
        `'lbfgs'` uses an update formula based on gradient information to
        estimate the Hessian. The upshot of this is that the convergence
        rate (the number of iterations needed to reach convergence) is
        typically better for `'trust_region'`, though each iteration
        typically takes longer to generate. By default, it is advised to
        use `'trust_region'`, however if your guess has a large number
        of signals, you may find `'lbfgs'` performs more effectively.

        See Also
        --------
        :py:class:`nmrespy.nlp.nlp.NonlinearProgramming`
        """

        # TODO: include freq threshold

        data, sw, offset = self._get_data_sw_offset()
        kwargs['offset'] = offset
        kwargs['sfo'] = self.get_sfo(kill=False)

        if trim is None:
            trim = [s for s in data.shape]

        ArgumentChecker([(trim, 'trim', 'int_list')], dim=self.dim)

        trim = tuple(np.s_[0:t] for t in trim)
        # Slice data
        data = data[trim]

        mpm_info = self.get_mpm_info()
        x0 = mpm_info.result

        self.nlp_info = NonlinearProgramming(data, x0, sw, **kwargs)

    def get_nlp_info(self, kill=True):
        """Returns information relating to nonlinear programming.

        Parameters
        ----------
        kill : bool, default: True
            If `self.nlp_info` is `None`, and `kill` is `True`, an error will
            be raised. If `kill` is False, `None` will be returned.

        Returns
        -------
        nlp_info : :py:class:`nmrespy.filter.NonlinearProgramming`
        """

        return self._check_if_none(
            'nlp_info', kill, method='nonlinear_programming'
        )

    @logger
    def write_result(self, **kwargs):
        """Saves an estimation result to a file in a human-readable format
        (text, PDF, CSV).

        Parameters
        ----------
        kwargs : Properties of :py:func:`nmrespy.write.write_result`.
        Valid arguments are:

        * `path`
        * `description`
        * `sig_figs`
        * `sci_lims`
        * `fmt`
        * `force_overwrite`

        Other keyword arguments that are valid in
        :py:func:`nmrespy.write.write_result` will be ignored (these are
        generated internally by the class instance).

        Raises
        ------
        AttributeIsNoneError
            If no parameter estimate derived from nonlinear programming
            is found (see :py:meth:`nonlinear_programming`).

        See Also
        --------
        :py:func:`nmrespy.write.write_result`
        """

        # Remove any invalid arguments from kwargs (avoid repetition
        # in call to nmrespy.write.write_result)
        for key in ['sfo', 'integrals', 'info', 'info_headings']:
            try:
                kwargs.pop(key)
            except KeyError:
                pass

        # Retrieve result
        # If nonlinear_programming has not been run yet, this will be
        # caught by get_nlp_info
        result = self.get_nlp_info().get_result()

        # Information for experiment info
        sw_h = self.get_sw()
        sw_p = self.get_sw(unit='ppm')
        off_h = self.get_offset()
        off_p = self.get_offset(unit='ppm')
        sfo = self.get_sfo(kill=False)
        bf = self.get_bf(kill=False)
        nuc = self.get_nucleus(kill=False)
        region_h = self.get_filter_info(kill=False).get_region(unit='hz')
        region_p = self.get_filter_info(kill=False).get_region(unit='ppm')

        # Peak integrals
        integrals = [
            signal.oscillator_integral(osc, self.get_n(), sw_h, offset=off_h)
            for osc in result
        ]

        # --- Package experiment information ----------------------------
        info_headings = []
        info = []
        sigfig = 6
        if self.get_dim() == 1:
            # Sweep width
            info_headings.append('Sweep Width (Hz)')
            info.append(str(significant_figures(sw_h[0], sigfig)))
            if sw_p is not None:
                info_headings.append('Sweep Width (ppm)')
                info.append(str(significant_figures(sw_p[0], sigfig)))

            # Offset
            info_headings.append('Transmitter Offset (Hz)')
            info.append(str(significant_figures(off_h[0], sigfig)))
            if off_p is not None:
                info_headings.append('Transmitter Offset (ppm)')
                info.append(str(significant_figures(off_p[0], sigfig)))

            # Transmitter frequency
            if sfo is not None:
                info_headings.append('Transmitter Frequency (MHz)')
                info.append(str(significant_figures(sfo[0], sigfig)))

            # Basic frequency
            if bf is not None:
                info_headings.append('Basic Frequency (MHz)')
                info.append(str(significant_figures(bf[0], sigfig)))

            # Nuclei
            if nuc is not None:
                info_headings.append('Nucleus')
                # Extract the isotope number from the element symbol
                # \d+ matches any number of consecutive numerical values,
                # starting from the beginning of the string.
                info.append(latex_nucleus(nuc[0]))

            # Region
            if region_h is not None:
                info_headings.append('Filter region (Hz):')
                info.append(
                    f'{significant_figures(region_h[0][0], sigfig)} -'
                    f' {significant_figures(region_h[0][1], sigfig)}'
                )
            if region_p is not None:
                info_headings.append('Filter region (ppm):')
                info.append(
                    f'{significant_figures(region_p[0][0], sigfig)} -'
                    f' {significant_figures(region_p[0][1], sigfig)}'
                )

        # TODO
        elif self.get_dim() == 2:
            raise TwoDimUnsupportedError()

        write_result(
            result, integrals=integrals, info_headings=info_headings,
            info=info, sfo=sfo, **kwargs,
        )

    def plot_result(self, result_name=None, datacol=None, osccols=None,
                    labels=True, stylesheet=None):
        """Generates a figure with the result of an estimation routine.
        A spectrum of the original data is plotted, along with the
        Fourier transform of each individual oscillator that makes up the
        estimation result.

        .. note::
            Currently, this method is only compatible with 1-dimesnional
            data.

        Parameters
        ----------
        result_name : None, 'theta', or 'theta0', default: None
            The parameter array to use. If ``None``, the parameter estimate
            to use will be determined in the following order of priority:

            1. ``self.theta`` will be used if it is not ``None``.
            2. ``self.theta0`` will be used if it is not ``None``.
            3. Otherwise, an error will be raised.

        datacol : matplotlib color or None, default: None
            The color used to plot the original data. Any value that is
            recognised by matplotlib as a color is permitted. See:

            https://matplotlib.org/3.1.0/tutorials/colors/colors.html

            If ``None``, the default color :grey:`#808080` will be used.

        osccols : matplotlib color, matplotlib colormap, list, or None,\
        default: None
            Describes how to color individual oscillators. The following
            is a complete list of options:

            * If the value denotes a matplotlib color, all oscillators will
              be given this color.
            * If a string corresponding to a matplotlib colormap is given,
              the oscillators will be consecutively shaded by linear increments
              of this colormap.
              For all valid colormaps, see:

              https://matplotlib.org/3.3.1/tutorials/colors/colormaps.html
            * If a list or NumPy array containing valid matplotlib colors is
              given, these colors will be cycled.
              For example, if ``osccols=['r', 'g', 'b']``:

              + Oscillators 1, 4, 7, ... would be :red:`red (#FF0000)`
              + Oscillators 2, 5, 8, ... would be :green:`green (#008000)`
              + Oscillators 3, 6, 9, ... would be :blue:`blue (#0000FF)`

            * If ``None``, the default colouring method will be applied,
              which involves cycling through the following colors:

              + :oscblue:`#1063E0`
              + :oscorange:`#EB9310`
              + :oscgreen:`#2BB539`
              + :oscred:`#D4200C`

        labels : Bool, default: True
            If ``True``, each oscillator will be given a numerical label
            in the plot, if ``False``, no labels will be produced.

        stylesheet : None or str, default: None
            The name of/path to a matplotlib stylesheet for further
            customisation of the plot. Note that all the features of the
            stylesheet will be adhered to, except for the colors, which are
            overwritten by whatever is specified by ``datacol`` and
            ``osccols``. If ``None``, a custom stylesheet, found in the
            follwing path is used:

            ``/path/to/NMR-EsPy/nmrespy/config/nmrespy_custom.mplstyle``

            To see built-in stylesheets that are available, enter
            the following into a python interpreter: ::
                >>> import matplotlib.pyplot as plt
                >>> print(plt.style.available)
            Alternatively, enter the full path to your own custom stylesheet.

        Returns
        -------
        fig : `matplotlib.figure.Figure <https://matplotlib.org/3.3.1/\
        api/_as_gen/matplotlib.figure.Figure.html>`_
            The resulting figure.

        ax : `matplotlib.axes._subplots.AxesSubplot <https://matplotlib.org/\
        3.3.1/api/axes_api.html#the-axes-class>`_
            The resulting set of axes.

        lines : dict
            A dictionary containing a series of
            `matplotlib.lines.Line2D <https://matplotlib.org/3.3.1/\
            api/_as_gen/matplotlib.lines.Line2D.html>`_
            instances. The data plot is given the key ``'data'``, and the
            individual oscillator plots are given the keys ``'osc1'``,
            ``'osc2'``, ``'osc3'``, ..., ``'osc<M>'`` where ``<M>`` is the
            number of oscillators in the parameter estimate.

        labs : dict
            If ``labels`` is True, this dictionary will contain a series
            of `matplotlib.text.Text <https://matplotlib.org/3.1.1/\
            api/text_api.html#matplotlib.text.Text>`_ instances, with the
            keys ``'osc1'``, ``'osc2'``, etc. as is the case with the
            ``lines`` dictionary. If ``labels`` is False, ``labs`` will be
            and empty dictionary.

        Raises
        ------
        TwoDimUnsupportedError
            If ``self.dim`` is 2.

        NoParameterEstimateError
            If ``result_name`` is ``None``, and both ``self.theta0`` and
            ``self.theta`` are ``None``.

        Notes
        -----
        The ``fig``, ``ax``, ``lines`` and ``labels`` objects that are returned
        provide the ability to customise virtually any feature of the plot. If
        you wish to edit a particular line or label, simply use the following
        syntax: ::
            >>> fig, ax, lines, labs = example.plot_result()
            >>> lines['osc7'].set_lw(1.6) # set oscillator 7's linewith to 2
            >>> labs['osc2'].set_x(4) # move the x co-ordinate of oscillator 2's label to 4ppm

        To save the figure, simply use `savefig: <https://matplotlib.org/\
        3.1.1/api/_as_gen/matplotlib.pyplot.savefig.html>`_
        ::
            >>> fig.savefig('example_figure.pdf', format='pdf')
        """

        dim = self.get_dim()
        # check dim is valid (only 1D data supported so far)
        if dim == 2:
            raise TwoDimUnsupportedError()

        result, result_name = self._check_result(result_name)

        data = fftshift(fft(self.data))[::-1]

        # phase data
        p0 = self.get_p0(kill=False)
        p1 = self.get_p1(kill=False)

        if p0 is None:
            pass
        else:
            data = _ve.phase(data, p0, p1)

        # FTs of FIDs generated from individual oscillators in result array
        peaks = []
        for m, osc in enumerate(result):
            f = self.make_fid(result_name, oscillators=[m])
            peaks.append(np.real(fftshift(fft(f))))

        # left and right boundaries of filter region
        region = self.get_region(kill=False)

        nuc = self.get_nucleus()
        shifts = self.get_shifts(unit='ppm')

        return _plot.plotres_1d(
            data, peaks, shifts, region, nuc, datacol, osccols, labels,
            stylesheet
        )


    @logger
    def add_oscillators(self, oscillators, result_name=None):
        """Adds new oscillators to a parameter array.

        Parameters
        ----------
        oscillators : numpy.ndarray
            An array of the new oscillator(s) to add to the array. The array
            should be of shape (I, 4) or (I, 6), where I is greater than 0.

        result_name : None, 'theta', or 'theta0', default: None
            The parameter array to use. If ``None``, the parameter estimate
            to use will be determined in the following order of priority:

            1. ``self.theta`` will be used if it is not ``None``.
            2. ``self.theta0`` will be used if it is not ``None``.
            3. Otherwise, an error will be raised.
        """

        self._log_method()

        if isinstance(oscillators, np.ndarray):
            # if oscillators is 1D, convert to 2D array
            if oscillators.ndim == 1:
                oscillators = oscillators.reshape(-1, oscillators.shape[0])

            # number of parameters per oscillator (should be 4 for 1D, 6 for 2D)
            num = oscillators.shape[1]
            # expected number of parameters per oscillator
            exp = 2 * self.get_dim() + 2

            if num == exp:
                pass
            else:
                msg = f'\n{R}oscillators should have a size of {exp} along' \
                      + f' axis-1{END}'
                raise ValueError(msg)

        else:
            raise TypeError(f'\n{R}oscillators should be a numpy array{END}')

        result, result_name = self._check_result(result_name)

        result = np.append(result, oscillators, axis=0)
        self.__dict__[result_name] = result[np.argsort(result[..., 2])]


    @logger
    def remove_oscillators(self, indices, result_name=None):
        """Removes the oscillators corresponding to ``indices``.

        Parameters
        ----------
        indices : list, tuple or numpy.ndarray
            A list of indices corresponding to the oscillators to be removed.

        result_name : None, 'theta', or 'theta0', default: None
            The parameter array to use. If ``None``, the parameter estimate
            to use will be determined in the following order of priority:

            1. ``self.theta`` will be used if it is not ``None``.
            2. ``self.theta0`` will be used if it is not ``None``.
            3. Otherwise, an error will be raised.
        """

        self._log_method()

        if isinstance(indices, (tuple, list, np.ndarray)):
            pass
        else:
            raise TypeError(f'\n{R}indices does not have a suitable type{END}')

        result, result_name = self._check_result(result_name)

        try:
            result = np.delete(result, indices, axis=0)
        except:
            msg = f'{R}oscillator removal failed. Check the values in' \
                  + f' indices are valid.{END}'
            raise ValueError(msg)

        self.__dict__[result_name] = result[np.argsort(result[..., 2])]
        print(self.__dict__[result_name])


    @logger
    def merge_oscillators(self, indices, result_name=None):
        """Removes the oscillators corresponding to ``indices``, and
        constructs a single new oscillator with a cumulative amplitude, and
        averaged phase, frequency and damping factor.

        .. note::
            Currently, this method is only compatible with 1-dimesnional
            data.

        Parameters
        ----------
        indices : list, tuple or numpy.ndarray
            A list of indices corresponding to the oscillators to be merged.

        result_name : None, 'theta', or 'theta0', default: None
            The parameter array to use. If ``None``, the parameter estimate
            to use will be determined in the following order of priority:

            1. ``self.theta`` will be used if it is not ``None``.
            2. ``self.theta0`` will be used if it is not ``None``.
            3. Otherwise, an error will be raised.

        Notes
        -----
        Assuming that an estimation result contains a subset of oscillators
        denoted by indices :math:`\{m_1, m_2, \cdots, m_J\}`, where
        :math:`J \leq M`, the new oscillator formed by the merging of the
        oscillator subset will possess the follwing parameters:

            * :math:`a_{\\mathrm{new}} = \\sum_{i=1}^J a_{m_i}`
            * :math:`\\phi_{\\mathrm{new}} = \\frac{1}{J} \\sum_{i=1}^J \\phi_{m_i}`
            * :math:`f_{\\mathrm{new}} = \\frac{1}{J} \\sum_{i=1}^J f_{m_i}`
            * :math:`\\eta_{\mathrm{new}} = \\frac{1}{J} \\sum_{i=1}^J \\eta_{m_i}`
        """

        self._log_method()

        # determine number of elements in indices
        # if fewer than 2 elements, return without doing anything
        if isinstance(indices, (tuple, list, np.ndarray)):
            number = len(indices)
            if number < 2:
                msg = f'\n{O}indices should contain at least two elements.' \
                      + f'No merging will happen.{END}'
                return
        else:
            raise TypeError(f'\n{R}indices does not have a suitable type{END}')

        result, result_name = self._check_result(result_name)

        to_merge = result[indices]
        new_osc = np.sum(to_merge, axis=0, keepdims=True)

        # get mean for phase, frequency and damping
        new_osc[:, 1:] = new_osc[:, 1:] / number

        result = np.delete(result, indices, axis=0)
        result = np.append(result, new_osc, axis=0)
        self.__dict__[result_name] = result[np.argsort(result[..., 2])]


    @logger
    def split_oscillator(self, index, result_name=None, frequency_sep=2.,
                         unit='hz', split_number=2, amp_ratio='same'):
        """Removes the oscillator corresponding to ``index``. Incorporates two
        or more oscillators whose cumulative amplitudes match that of the
        removed oscillator.

        .. note::
            Currently, this method is only compatible with 1-dimesnional
            data.

        Parameters
        ----------
        index : int
            Array index of the oscilator to be split.

        result_name : None, 'theta', or 'theta0', default: None
            The parameter array to use. If ``None``, the parameter estimate
            to use will be determined in the following order of priority:

            1. ``self.theta`` will be used if it is not ``None``.
            2. ``self.theta0`` will be used if it is not ``None``.
            3. Otherwise, an error will be raised.

        frequency_sep : float, default: 2.
            The frequency separation given to adjacent oscillators formed from
            splitting.

        unit : 'hz' or 'ppm', default: 'hz'
            The unit of ``frequency_sep``.

        split_number: int, default: 2
            The number of peaks to split the oscillator into.

        amp_ratio: list or 'same', default: 'same'
            The ratio of amplitudes to be fulfilled by the newly formed peaks.
            If a list, ``len(amp_ratio) == split_number`` must be
            ``True``. The first element will relate to the highest frequency
            oscillator constructed (furthest to the left in a conventional
            spectrum), and the last element will relate to the lowest
            frequency oscillator constructed. If ``'same'``, all oscillators
            will be given equal amplitudes.
        """

        # get frequency_Sep in correct units
        if unit == 'hz':
            pass
        elif unit == 'ppm':
            frequency_sep = frequency_sep * self.get_sfo()
        else:
            raise errors.InvalidUnitError('hz', 'ppm')

        result, result_name = self._check_result(result_name)

        try:
            osc = result[index]
        except:
            raise ValueError(f'{R}index should be an int in'
                             f' range({result.shape[0]}){END}')

        # lowest frequency of all the new oscillators
        max_freq = osc[2] + ((split_number - 1) * frequency_sep / 2)
        # array of all frequencies (lowest to highest)
        freqs = [max_freq - (i*frequency_sep) for i in range(split_number)]

        # determine amplitudes of new oscillators
        if amp_ratio == 'same':
            amp_ratio = [1] * split_number

        if isinstance(amp_ratio, list):
            pass
        else:
            raise TypeError(f'{R}amp_ratio should be \'same\' or a list{END}')

        if len(amp_ratio) == split_number:
            pass
        else:
            raise ValueError(f'{R}len(amp_ratio) should equal'
                             f' split_number{END}')

        # scale amplitude ratio values such that their sum is 1
        amp_ratio = np.array(amp_ratio)
        amp_ratio = amp_ratio / np.sum(amp_ratio)

        # obtain amplitude values
        amps = osc[0] * amp_ratio

        new_oscs = np.zeros((split_number, 4))
        new_oscs[:, 0] = amps
        new_oscs[:, 2] = freqs
        new_oscs[:, 1] = [osc[1]] * split_number
        new_oscs[:, 3] = [osc[3]] * split_number

        result = np.delete(result, index, axis=0)
        result = np.append(result, new_oscs, axis=0)
        self.__dict__[result_name] = result[np.argsort(result[..., 2])]


    def save_logfile(self, path='./nmrespy_log', force_overwrite=False):
        """Saves log file of class instance usage to a specified path.

        Parameters
        ----------
        path : str, default: './nmrespy_log'
            The path to save the file to. DO NOT INCLUDE A FILE EXTENSION.
            `.log` will be added automatically.

        force_overwrite : bool. default: False
            Defines behaviour if ``f'{path}.log'`` already exists:

            * If `force_overwrite` is set to `False`, the user will be prompted
              if they are happy overwriting the current file.
            * If `force_overwrite` is set to `True`, the current file will be
              overwritten without prompt.
        """

        ArgumentChecker(
            [
                (path, 'path', 'str'),
                (force_overwrite, 'force_overwrite', 'bool'),
            ]
        )

        # Get full path and extend .log extension
        path = Path(path).resolve().with_suffix('.log')
        # Check path is valid (check directory exists, ask user if they are happy
        # overwriting if file already exists).
        pathres = PathManager(path.name, path.parent).check_file(force_overwrite)
        # Valid path, we are good to proceed
        if pathres == 0:
            pass
        # Overwrite denied by the user. Exit the program
        elif pathres == 1:
            exit()
        # pathres == 2: Directory specified doesn't exist
        else:
            raise ValueError(
                f'{cols.R}The directory implied by path does not'
                f' exist{cols.END}'
            )

        try:
            shutil.copyfile(self._logpath, path)
            print(
                f'{cols.G}Log file succesfully saved to'
                f' {str(path)}{cols.END}'
            )

        # trouble copying file...
        except Exception as e:
            raise e



    @staticmethod
    def _check_int_float(param):
        """Check if param is a float or int. If it is, convert to a tuple"""

        if isinstance(param, (float, int)):
            return param,

        return param

    def _check_data_sw_offset(self):
        """Returns time-domain data, sweep width and offset.

        Returns
        -------
        data : np.ndarray
            The time-domain signal.

        sw : [float] or [float, float]
            The sweep width in each dimension.

        offset : [float] or [float, float]
            The offset in each dimension.

        Notes
        -----
        The following hierarchical order is used to determine `data`, `sw`
        and `offset`:

        * If a filtered signal is present, this is returned as `data`.
        * Otherwise, the originally imported data is returned.

        The appropriate sweep width and offset values are returned, based
        on whether the the filtered signal was cut (see
        :py:meth:`frequency_filter` for more info).
        """

        # check whether filtered_signal signal is None or not
        filtered_signal = self.get_filtered_signal(kill=False)
        if isinstance(filtered_signal, np.ndarray):
            print('yep')
            # not None -> return filtred signal
            data = filtered_signal

            # check whether filtered_sw is None or not
            if self.get_filtered_sw(kill=False):
                return data, self.get_filtered_sw(), self.get_filtered_offset()

            return data, self.get_sw(), self.get_offset()

        # None -> return original data, sw, and offset
        return self.get_data(), self.get_sw(), self.get_offset()


    def _check_result(self, result_name):

        if result_name is None:
            for attr in ['theta', 'theta0']:
                result = getattr(self, attr)
                if isinstance(result, np.ndarray):
                    return result, attr

            raise NoParameterEstimateError()

        elif result_name in ['theta', 'theta0']:
            result = getattr(self, result_name)
            if isinstance(result, np.ndarray):
                return result, result_name
            else:
                raise ValueError(f'{R}{result_name} does not correspond to a valid'
                                 f' estimation result (it should be a numpy'
                                 f' array). Perhaps you have forgotten a step'
                                 f' in generating the parameter estimate?{END}')
        else:
            raise ValueError(f'{R}result_name should be None, \'theta\', or'
                             f' \'theta0\'{END}')

    def _check_trim(self, trim, data):
        if trim != None:
            trim = self._check_int_float(trim)
            # check trim is not larger than full signal size in any dim
            for i, (t, n) in enumerate(zip(trim, data.shape)):
                if t <= n:
                    pass
                else:
                    msg = f'\n{R}trim value is invalid. Ensure that each' \
                          + f' element in trim in smaller than or equal to' \
                          + f' the corresponding data shape in that' \
                          + f' dimension.\n' \
                          + f'trim: {trim}   data shape: {data.shape}{END}\n'
                    raise ValueError(msg)
            return trim

        else:
            return data.shape
