# -*- coding: utf-8 -*-


from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import
from __future__ import print_function

import warnings
from functools import reduce

import numpy as np
import pandas as pd

from pandas.io import pytables

from .measures.transformation import time_interpolate as time_interpolate_
from .measures.transformation import transformations_matrix
from ..utils import print_progress

import logging
log = logging.getLogger(__name__)


__all__ = []


class Trajectories(pd.DataFrame):
    """
    This class is a subclass of the class :class:`pandas.DataFrame`.

    It is mainly here to provide utility attributes and syntactic shugar.

    Attributes
    ----------
    t_stamps : ndarray
        unique values of the `t_stamps` index of `self.trajs`

    labels : ndarray
        unique values of the `labels` index of `self.trajs`

    iter_segments : iterator
        yields a `(label, segment)` pair where `label` is iterated over `self.labels`
        and `segment` is a chunk of `self.trajs`

    segment_idxs : dictionnary
        Keys are the segent label and values are a list
        of  `(t_stamp, label)` tuples for each time point of the segment

    Parameters
    ----------
    trajs : :class:`pandas.DataFrame`

    Examples
    --------
    >>> from sktracker import data
    >>> from sktracker.trajectories import Trajectories
    >>>
    >>> trajs = data.with_gaps_df()
    >>> trajs = Trajectories(trajs)
    >>>
    >>> # One of the available method can display trajectories with matplotlib.
    >>> trajs.show(xaxis='t', yaxis='x')
    <matplotlib.axes.AxesSubplot at 0x7f027ecc2cf8>

    """
    def __init__(self, *args, **kwargs):
        """
        """
        super(self.__class__, self).__init__(*args, **kwargs)

    @classmethod
    def empty_trajs(cls, columns=['x', 'y', 'z']):
        empty_index = pd.MultiIndex.from_arrays(np.empty((2, 0)),
                                                names=['t_stamp', 'label'])
        empty_trajs = pd.DataFrame(np.empty((0, len(columns))),
                                   index=empty_index,
                                   columns=columns)
        return cls(empty_trajs)

    def check_trajs_df_structure(self, index=None, columns=None):
        """Check wether trajectories contains a specified structure.

        Parameters
        ----------
        index : list
            Index names (order is important)
        columns : list
            Column names (order does not matter here)

        Raises
        ------
        ValueError in both case
        """

        error_mess = "Trajectories does not contain correct indexes : {}"
        if index and self.index.names != index:
            raise ValueError(error_mess.format(index))

        error_mess = "Trajectories does not contain correct columns : {}"
        if columns:
            columns = set(columns)
            if not columns.issubset(set(self.columns)):
                raise ValueError(error_mess.format(columns))

    # Trajs getter methods

    @property
    def t_stamps(self):
        return self.index.get_level_values('t_stamp').unique()

    @property
    def labels(self):
        if 'label' in self.columns:
            return self['label'].unique()
        else:
            return self.index.get_level_values('label').unique()

    @property
    def segment_idxs(self):
        return self.groupby(level='label').groups

    @property
    def iter_segments(self):
        for lbl, idxs in self.segment_idxs.items():
            yield lbl, self.loc[idxs]

    def get_bounds(self, column=None):
        """Get bounds of all segments.

        Parameters
        ----------
        column : string
            By default the method will return bounds as 't_stamp'. If you want another value from
            column ('t' for example), you can put the column's name here.
        asarray : bool
            Return bounds as dict of as array wether it's True

        Returns
        -------
        bounds as dict or ndarray
        """
        all_segs = self.segment_idxs.items()
        if column:
            bounds = {k: (self.loc[v[0], column], self.loc[v[-1], column]) for k, v in all_segs}
        else:
            bounds = {k: (v[0][0], v[-1][0]) for k, v in all_segs}
        return bounds

    def get_segments(self):
        """A segment contains all the data from `self.trajs` with

        Returns
        -------
        A dict with labels as keys and segments as values
        """
        return {key: segment for key, segment
                in self.iter_segments}

    def get_longest_segments(self, n):
        """Get the n th longest segments label indexes.

        Parameters
        ----------
        n : int
        """
        idxs = self.segment_idxs
        return list(dict(sorted(idxs.items(), key=lambda x: len(x[1]))[-n:]).keys())

    def get_shortest_segments(self, n):
        """Get the n th shortest segments label indexes.

        Parameters
        ----------
        n : int
        """
        idxs = self.segment_idxs
        return list(dict(sorted(idxs.items(), key=lambda x: len(x[1]))[:n]).keys())

    def copy(self):
        """
        """

        trajs = super(self.__class__, self).copy()
        return Trajectories(trajs)

    def get_colors(self, cmap="hsv", alpha=None, rgba=False):
        '''Get color for each label.

        Parameters
        ----------
        cmap : string
            See http://matplotlib.org/examples/color/colormaps_reference.html for a list of
            available colormap.
        alpha : float
            Between 0 and 1 to add transparency on color.
        rgba : bool
            If True return RGBA tuple for each color. If False return HTML color code.

        Returns
        -------
        dict of `label : color` pairs for each segment.
        '''
        import matplotlib.pyplot as plt
        cmap = plt.cm.get_cmap(name=cmap)

        n = len(self.labels)
        ite = zip(np.linspace(0, 0.9, n), self.labels)
        colors = {label: cmap(i, alpha=alpha) for i, label in ite}

        if not rgba:
            def get_hex(rgba):
                rgba = np.round(np.array(rgba) * 255).astype('int')
                if not alpha:
                    rgba = rgba[:3]
                return "#" + "".join(['{:02X}'.format(a) for a in rgba])

            colors = {label: get_hex(color) for label, color in colors.items()}

        return colors

    def get_t_stamps_correspondences(self, data_values, column):
        """For a given column return 't_stamp' values corresponding to 1d vector of this column.

        Parameters
        ----------
        data_values : 1d np.ndarray
            Data found in self[column]
        column : str
            Which column to use.

        Returns
        -------
        np.ndarray with the same length as 'data_values'.
        """

        t_stamps = self.t_stamps
        values = self[column].unique()

        index = np.argsort(values)
        values_sorted = values[index]
        sorted_index = np.searchsorted(values_sorted, data_values)

        yindex = np.take(index, sorted_index)

        return t_stamps[yindex]

    # Segment / spot modification methods

    def remove_spots(self, spots, inplace=False):
        """Remove spots identified by (t_stamp, label).

        Parameters
        ----------
        spots : tuple or list of tuple
            Each tuple must contain (t_stamp, label) to remove.

        Returns
        -------
        Copy of modified trajectories or None wether inplace is True.
        """
        return Trajectories(self.drop(spots, inplace=inplace))

    def remove_segments(self, segments_idx, inplace=False):
        """Remove segments from trajectories.

        Parameters
        ----------
        segments_idx : list
            List of label to remove
        """
        return Trajectories(self.drop(segments_idx, level='label', inplace=inplace))

    def merge_segments(self, labels, inplace=False):
        """Merge segments from a list of labels. If spots have the same t_stamp, only the first spot
        for the t_stamp is keept (we may want to reconsider that behaviour later).

        Parameters
        ----------
        labels : list
            Labels to merge.

        Returns
        -------
        Copy of modified trajectories or None wether inplace is True.
        """

        if inplace:
            trajs = self
        else:
            trajs = self.copy()

        new_label = labels[0]

        trajs.sortlevel(inplace=True)
        trajs.loc[:, 'new_label'] = trajs.index.get_level_values('label').values

        idx = pd.IndexSlice
        for label in labels[1:]:
            trajs.loc[idx[:, label], 'new_label'] = new_label

        trajs.reset_index('label', inplace=True)
        trajs.drop('label', axis=1, inplace=True)
        trajs.rename(columns={'new_label': 'label'}, inplace=True)
        trajs.set_index('label', append=True, inplace=True)
        trajs.sortlevel(inplace=True)

        # Remove duplicate spots from the same t_stamp
        gps = trajs.groupby(level=['t_stamp', 'label'])
        trajs = Trajectories(gps.apply(lambda x: x.iloc[0]))

        if inplace:
            return None
        else:
            return trajs

    def cut_segments(self, spot, inplace=False):
        """Cut segment. All spots with same label as `spot` and with `t_stamp` greater than
        `spot` will have a new label.

        Parameters
        ----------
        spot : tuple
            Must contain (t_stamp, label)

        Returns
        -------
        Copy of modified trajectories or None wether inplace is True.
        """

        if inplace:
            trajs = self
        else:
            trajs = self.copy()

        trajs.sortlevel(inplace=True)
        t_stamp, label = spot
        new_label = trajs.index.get_level_values('label').max() + 1

        trajs.loc[:, 'new_label'] = trajs.index.get_level_values('label').values

        idxs = (trajs.index.get_level_values('t_stamp') > t_stamp) & (trajs.index.get_level_values('label') == label)
        trajs.loc[idxs, 'new_label'] = new_label

        trajs.reset_index('label', inplace=True)
        trajs.drop('label', axis=1, inplace=True)
        trajs.rename(columns={'new_label': 'label'}, inplace=True)
        trajs.set_index('label', append=True, inplace=True)
        trajs.sortlevel(inplace=True)

        if inplace:
            return None
        else:
            return trajs

    def duplicate_segments(self, label):
        """Duplicate segment.

        Parameters
        ----------
        label : int
            Label index.

        Returns
        -------
        Copy of modified :class:`sktracker.trajectories.Trajectories` or None wether inplace is
        True.
        """

        trajs = self.copy()

        new_label = trajs.labels.max() + 1
        index_names = trajs.index.names
        trajs.reset_index(inplace=True)

        new_segment = trajs[trajs['label'] == label].copy()
        new_segment.loc[:, 'label'] = new_label

        trajs = Trajectories(pd.concat([trajs, new_segment]))

        trajs.set_index(index_names, inplace=True)
        trajs.sort_index(inplace=True)

        return trajs

    # All trajectories modification methods

    def set_level_label(self, inplace=True):
        """If 'label' is a column then reset index (except 't_stamp') and then put 'label' in index.
        """

        if inplace:
            trajs = self
        else:
            trajs = self.copy()

        if 'label' not in self.columns:
            log.error("'label' not in columns. Can't set level 'label'.")
        else:
            trajs.old_indexes = list(trajs.index.names)
            trajs.old_indexes.remove('t_stamp')
            trajs.reset_index(trajs.old_indexes, inplace=True)
            trajs.set_index('label', append=True, inplace=True)

        if inplace:
            return None
        else:
            return trajs

    def unset_level_label(self, cols=[], inplace=True):
        """Reset original indexes (set 'label' as column).
        """

        if inplace:
            trajs = self
        else:
            trajs = self.copy()

        if len(cols) == 0 and not hasattr(self, 'old_indexes'):
            log.error("""No original indexes found or 'cols' not provided."""
                      """Can't unset level 'label'""")
            return None

        if len(cols) == 0:
            cols = self.old_indexes

        trajs.reset_index('label', inplace=True)
        trajs.set_index(cols, append=True, inplace=True)

        if inplace:
            return None
        else:
            return trajs

    def reverse(self, time_column='t', inplace=False):
        """Reverse trajectories time.

        Parameters
        ----------
        time_column : str
            Which column used to reverse.

        Returns
        -------
        Copy of modified :class:`sktracker.trajectories.Trajectories` or None wether inplace is
        True.
        """

        if inplace:
            trajs = self
        else:
            trajs = self.copy()

        trajs.reset_index(inplace=True)
        trajs['t_stamp'] = trajs['t_stamp'] * -1
        trajs[time_column] = trajs[time_column] * -1
        trajs.sort('t_stamp', inplace=True)
        trajs.set_index(['t_stamp', 'label'], inplace=True)

        if inplace:
            return None
        else:
            return trajs

    def merge_label_safe(self, traj, id=None):  # pragma: no cover
        """See Trajectories.merge instead
        """
        mess = "`merge_label_safe` has been renamed to `merge`."
        warnings.warn(mess, DeprecationWarning)

        return self.merge(traj, id=id)

    def merge(self, traj, id=None):
        """Merge traj to self trajectories taking care to not mix labels between them.

        Parameters
        ----------
        traj : :class:`pandas.DataFrame` or :class:`sktracker.trajectories.Trajectories`

        Returns
        -------
        Copy of modified :class:`sktracker.trajectories.Trajectories` or None wether inplace is
        True.
        """

        traj = traj.reset_index()
        self = self.reset_index()

        self_label = set(self['label'])
        traj_label = set(traj['label'])

        same_labels = self_label.intersection(traj_label)

        if same_labels:
            new_label_start = max(traj_label.union(self_label)) + 1
            new_labels = np.arange(new_label_start, new_label_start + len(same_labels))
            self['label'] = self['label'].replace(list(same_labels), new_labels)

        if id:
            self['id'] = id[0]
            traj['id'] = id[1]

        new_trajs = Trajectories(pd.concat([self, traj]))

        # Relabel from zero
        old_lbls = new_trajs['label']
        nu_lbls = old_lbls.astype(np.uint16).copy()
        for n, uv in enumerate(old_lbls.unique()):
            nu_lbls[old_lbls == uv] = n

        new_trajs['label'] = nu_lbls

        new_trajs.set_index(['t_stamp', 'label'], inplace=True)
        new_trajs.sort_index(inplace=True)

        return new_trajs

    def relabel(self, new_labels=None, inplace=True):
        """Sets the trajectory index `label` to new values.

        Parameters
        ----------
        new_labels: :class:`numpy.ndarray` or None, default None
            The new label. If it is not provided, the function
            will look for a column named "new_label" in `trajs` and use this
            as the new label index

        Returns
        -------
        Copy of modified :class:`sktracker.trajectories.Trajectories` or None wether inplace is
        True.
        """

        if not inplace:
            trajs = self.copy()
        else:
            trajs = self

        if new_labels is not None:
            trajs['new_label'] = new_labels

        try:
            trajs.set_index('new_label', append=True, inplace=True)
        except KeyError:
            err = ('''Column "new_label" was not found in `trajs` and none'''
                   ''' was provided''')
            raise KeyError(err)

        trajs.reset_index(level='label', drop=True, inplace=True)
        trajs.index.set_names(['t_stamp', 'label'], inplace=True)
        trajs.sort_index(inplace=True)

        return trajs.relabel_fromzero('label', inplace=inplace)

    def relabel_fromzero(self, level='label', inplace=False):
        """
        Parameters
        ----------
        level : str
        inplace : bool

        Returns
        -------
        Copy of modified :class:`sktracker.trajectories.Trajectories` or None wether inplace is
        True.
        """

        if not inplace:
            trajs = self.copy()
        else:
            trajs = self

        old_lbls = self.index.get_level_values(level)
        nu_lbls = old_lbls.values.astype(np.uint16).copy()
        for n, uv in enumerate(old_lbls.unique()):
            nu_lbls[old_lbls == uv] = n

        trajs['new_label'] = nu_lbls

        trajs.set_index('new_label', append=True, inplace=True)
        trajs.reset_index(level, drop=True, inplace=True)

        index_names = list(trajs.index.names)
        index_names[index_names.index('new_label')] = level
        trajs.index.set_names(['t_stamp', 'label'], inplace=True)

        if inplace:
            return None
        else:
            return trajs

    def time_interpolate(self, sampling=1, s=0, k=3,
                         time_step=None,
                         keep_speed=True,
                         keep_acceleration=True,
                         coords=['x', 'y', 'z']):
        """
        Interpolates each segment of the trajectories along time
        using `scipy.interpolate.splrep`

        Parameters
        ----------
        sampling : int,
            Must be higher or equal than 1, will add `sampling - 1` extra points
            between two consecutive original data point. Sub-sampling is not supported.
        coords : tuple of column names, default `('x', 'y', 'z')`.
           The coordinates to interpolate. 'all' will interpolate all columns. If a coord is not a
           number then value will be just copied.
         s : float
            A smoothing condition. The amount of smoothness is determined by
            satisfying the conditions: sum((w * (y - g))**2,axis=0) <= s where g(x)
            is the smoothed interpolation of (x,y). The user can use s to control
            the tradeoff between closeness and smoothness of fit. Larger s means
            more smoothing while smaller values of s indicate less smoothing.
            Recommended values of s depend on the weights, w. If the weights
            represent the inverse of the standard-deviation of y, then a good s
            value should be found in the range (m-sqrt(2*m),m+sqrt(2*m)) where m is
            the number of datapoints in x, y, and w. default : s=m-sqrt(2*m) if
            weights are supplied. s = 0.0 (interpolating) if no weights are
            supplied.
        k : int
           The order of the spline fit. It is recommended to use cubic splines.
           Even order splines should be avoided especially with small s values.
           1 <= k <= 5

        Returns
        -------
        interpolated : a :class:`Trajectories` instance
           The interpolated values, with column names given by `coords`
           plus the computed speeds (first order derivative) and accelarations
           (second order derivative) if `k` > 2

        Notes
        -----
        The return trajectories are NOT indexed like the input (in particular for `t_stamp`)

        The `s` and `k` arguments are passed to `scipy.interpolate.splrep`, see this
             function documentation for more details
        If a segment is too short to be interpolated with the passed order `k`, the order
             will be automatically diminished
        Segments with only one point will be returned as is


        """
        if sampling is None and time_step is not None:
            log.warning(''' The `time_step` argument is deprecated (too fuzzy)'''
                        '''Use the `sampling` argument instead ''')
            dts = self.get_segments()[0].t.diff().dropna()
            dt = np.unique(dts)[0]
            if time_step > dt:
                raise NotImplementedError('''Subsampling is not supported, '''
                                          '''give a time_step bigger than the original''')
            sampling = np.int(dt/time_step)
            log.warning('''sampling was set to {} ({}/{})'''
                        .format(sampling, dt, time_step))

        if coords is 'all':
            coords_number = []
            coords_other = []
            for coord in self.columns:
                if self[coord].dtype.kind in ('i', 'f'):
                    coords_number.append(coord)
                else:
                    coords_other.append(coord)

            interpolated = time_interpolate_(self, sampling, s, k, coords_number)

            for coord in coords_other:
                interpolated[coord] = self[coord]

        else:

            interpolated = time_interpolate_(self, sampling, s, k, coords)

        if not keep_speed:
            for coord in interpolated.columns:
                if coord.startswith('v_'):
                    interpolated.drop(coord, axis=1, inplace=True)

        if not keep_acceleration:
            for coord in interpolated.columns:
                if coord.startswith('a_'):
                    interpolated.drop(coord, axis=1, inplace=True)

        return Trajectories(interpolated)

    def scale(self, factors, coords=['x', 'y', 'z'], inplace=False):
        '''Multiplies the columns given in coords by the values given in factors.
        The `factors` and `columns` must have the same length

        Parameters
        ----------
        factors : sequence of floats
            Values by which each colum will be multiplied
        columns : sequence of column indices, default ['x', 'y', 'z']
            Name of the columns to be scaled by factors
        inplace : bool, optional, default False
            If True, modifies the trajectories inplace, else returns a copy

        Returns
        -------

        The original trajectories scaled or a copy
        '''

        if len(factors) != len(coords):
            raise ValueError('''Arguments factors and coords must be of same length''')
        trajs = self if inplace else self.copy()
        for factor, coord in zip(factors, coords):
            trajs[coord] = trajs[coord] * factor
        return trajs

    def project(self, ref_idx,
                coords=['x', 'y'],
                keep_first_time=False,
                reference=None,
                inplace=False,
                progress=False):
        """Project each point on a line specified by two points.

        Parameters
        ----------
        ref_idx : list of int (length should be 2)
            This two series of points will be used as a reference line to make projection.
        coords :
            Column names.
        keep_first_time : bool
            By default reference line is computed for each timepoint. If you want to keep the first
            time stamp as reference line, put this parameter to True.
        reference :
            TODO
        inplace : bool
            Add projection inplace or to a new Trajectories
        progress : bool
            Show progress bar.

        Returns
        -------
        Trajectories with two new columns : 'x_proj', and 'y_proj'.
        """

        trajs = self if inplace else self.copy()
        trajs.sort_index(inplace=True)

        # First we check if both ref_idx are present in ALL t_stamp
        n_t = trajs.index.get_level_values('t_stamp').unique().shape[0]

        if len(coords) not in (2, 3):
            mess = "Length of coords {} is {}. Not supported number of dimensions"
            raise ValueError(mess.format(coords, len(coords)))

        trajs['x_proj'] = np.nan
        trajs['y_proj'] = np.nan

        ite = trajs.swaplevel("label", "t_stamp").groupby(level='t_stamp')
        A = None
        first_time = True
        for i, (t_stamp, peaks) in enumerate(ite):

            if progress:
                print_progress(i * 100 / n_t)

            peaks = peaks.sort_index()

            p1 = peaks.loc[ref_idx[0]][coords]
            p2 = peaks.loc[ref_idx[1]][coords]

            if p1.empty or p2.empty:
                trajs.loc[t_stamp, 'x_proj'] = np.nan
                trajs.loc[t_stamp, 'y_proj'] = np.nan
            else:
                if not keep_first_time or (keep_first_time and first_time):

                    if reference is None:
                        ref = (p1 + p2) / 2
                        vec = (p1 - ref).values[0]
                    else:
                        ref = [p1, p2][reference]
                        vec = (((p1 + p2) / 2) - ref).values[0]

                    ref = ref.values[0]
                    A = transformations_matrix(ref, vec)
                    first_time = False

                # Add an extra column if coords has two dimensions
                if len(coords) == 2:
                    peaks_values = np.zeros((peaks[coords].shape[0],
                                             peaks[coords].shape[1] + 1)) + 1
                    peaks_values[:, :-1] = peaks[coords].values
                elif len(coords) == 3:
                    peaks_values = peaks[coords].values

                # Apply the transformation matrix
                peaks_values = np.dot(peaks_values, A)[:, :-1]

                trajs.loc[t_stamp, 'x_proj'] = peaks_values[:, 0]
                trajs.loc[t_stamp, 'y_proj'] = peaks_values[:, 1]

        if progress:
            print_progress(-1)

        if np.abs(trajs.x_proj).median() < np.abs(trajs.y_proj).median():
            trajs.rename(columns={'x_proj': 'y_proj', 'y_proj': 'x_proj'}, inplace=True)

        trajs.sortlevel(inplace=True)

        # 'y_proj' should be close to 0
        idx = pd.IndexSlice
        ref_spots = trajs.loc[idx[:, ref_idx], 'y_proj'].dropna()
        if not np.allclose(ref_spots, 0):
            raise Exception("Projection failed. 'y_proj' is not equal to 0.")

        if not inplace:
            return trajs

    # Measures

    def get_diff(self, group_args={'level': 'label'},
                 columns=['t', 'x', 'y', 'z']):
        """Return the diff grouped by labels.

        Parameters
        ----------
        group_args : dict
            Used to group objects with :meth:`pandas.DataFrame.groupby`.
        columns : list
            Column names on which applying np.diff

        Returns
        -------
        diffs as :class:`pandas.DataFrame`
        """

        gp = self.groupby(**group_args)

        def get_distances(x):
            return np.diff(x)

        diffs = pd.DataFrame([])
        for coord in columns:
            diffs[coord] = gp[coord].apply(pd.rolling_apply, 2, get_distances)

        return diffs

    def get_speeds(self, time_column='t',
                   group_args={'level': 'label'},
                   coords=['x', 'y', 'z']):
        """Get instantaneous speeds between each spots on the same label.

        Parameters
        ----------
        time_column : str
            Column used to represents time.
        group_args : dict
            Used to group objects with :meth:`pandas.DataFrame.groupby`.
        coords : list
            Column names used to compute euclidean distance.

        Returns
        -------
        :class:`pandas.Series`
        """
        diffs = self.get_diff(group_args=group_args, columns=coords + [time_column])
        diffs[coords] = diffs[coords] ** 2

        speeds = reduce(pd.Series.__add__, [diffs[c] for c in coords])
        speeds /= np.abs(diffs[time_column])

        return speeds

    # Visualization methods

    def show(self, xaxis='t',
             yaxis='x',
             groupby_args={'level': "label"},
             ax=None, legend=False, **kwargs):  # pragma: no cover
        """Show trajectories

        Parameters
        ----------
        xaxis : str
        yaxis : str
        groupby : dict
            How to group trajectories
        ax : :class:`matplotlib.axes.Axes`
            None will create a new one.
        **kwargs are passed to the plot function

        Returns
        -------
        :class:`matplotlib.axes.Axes`

        Examples
        --------
        >>> from sktracker import data
        >>> from sktracker.tracker.solver import ByFrameSolver
        >>> import matplotlib.pylab as plt
        >>> true_trajs = data.brownian_trajectories_generator(p_disapear=0.1)
        >>> solver = ByFrameSolver.for_brownian_motion(true_trajs, max_speed=2)
        >>> trajs = solver.track(progress_bar=False)
        >>> fig, (ax1, ax2) = plt.subplots(nrows=2)
        >>> ax1 = trajs.show(xaxis='t', yaxis='x', groupby_args={'level': "label"}, ax=ax1)
        >>> ax2 = trajs.show(xaxis='t', yaxis='x', groupby_args={'by': "true_label"}, ax=ax2)

        """

        import matplotlib.pyplot as plt

        if ax is None:
            ax = plt.gca()
        colors = self.get_colors()
        gp = self.groupby(**groupby_args).groups

        # Set default kwargs if they are not provided
        # Unfortunately you can't pass somthing as '-o'
        # as a single linestyle kwarg

        if ((kwargs.get('ls') is None)
           and (kwargs.get('linestyle') is None)):
            kwargs['ls'] = '-'
        if kwargs.get('marker') is None:
            kwargs['marker'] = 'o'
        if ((kwargs.get('c') is None) and (kwargs.get('color') is None)):
            auto_color = True
        else:
            auto_color = False

        for k, v in gp.items():
            traj = self.loc[v]
            if auto_color:
                c = colors[v[0][1]]  # that's the label
                kwargs['color'] = c
            ax.plot(traj[xaxis], traj[yaxis], label=str(k), **kwargs)

        ax.set_xlabel(xaxis)
        ax.set_ylabel(yaxis)
        ax.set_title(str(groupby_args))

        if legend:
            ax.legend()

        return ax

    def show_4panels(self, label, coords=('x', 'y', 'z'),
                     axes=None, ax_3d=None,
                     scatter_kw={}, line_kw={},
                     interpolate=False, interp_kw={}):  # pragma: no cover
        '''Plots the segment of trajectories `trajs` with label `label` on four panels
        organized in two cols by two rows like so::


            y|     y|
             |___   |___
               x      z
            z|     z| y
             |___   |/__
               x      x


        Parameters
        ----------
        trajs: a :class:`Trajectories` instance
        label: int
           the label of the trajectories's segment to plot
        coords: a tuple of column names
           default to ('x', 'y', 'z'), the coordinates to plot
        axes: the axes to plot on
        ax_3d: the 3D ax on the lower right corner
        scatter_kw: dict
           keyword arguments passed to the `plt.scatter` function
        line_kw: dict
           keyword arguments passed to the `plt.plot` function
        interpolate: bool
           if True, will plot the line as an interpolation of
           the trajectories (not implemented right now)
        interp_kw: dict
           keyword arguments for the interpolation

        Returns
        -------
        axes, ax3d: the 2D and 3D axes
        '''
        import matplotlib.pyplot as plt

        u, v, w = coords

        segment = self.get_segments()[label]

        if interpolate:
            segment_i = self.time_interpolate(**interp_kw).get_segments()[label]
        else:
            segment_i = segment

        colors = self.get_colors()
        if 'c' not in scatter_kw and 'color' not in scatter_kw:
            scatter_kw['c'] = colors[label]
        if 'c' not in line_kw and 'color' not in line_kw:
            line_kw['c'] = colors[label]

        if axes is None:

            fig = plt.figure(figsize=(6, 6))
            ax2 = fig.add_subplot(222, aspect='equal')
            ax3 = fig.add_subplot(223, aspect='equal')
            ax1 = fig.add_subplot(221, sharey=ax2, sharex=ax3)

            ax_3d = fig.add_subplot(224, projection='3d')
            axes = np.array([[ax1, ax2], [ax3, ax_3d]])
            ax_3d.set_aspect('equal')

        for ax in axes.ravel():
            ax.set_aspect('equal')
            ax.grid()

        axes[0, 0].scatter(segment[u].values,
                           segment[v].values, **scatter_kw)
        axes[0, 1].scatter(segment[w].values,
                           segment[v].values, **scatter_kw)
        axes[1, 0].scatter(segment[u].values,
                           segment[w].values, **scatter_kw)
        if ax_3d is not None:
            ax_3d.scatter(segment[u].values,
                          segment[v].values,
                          segment[w].values, **scatter_kw)

        axes[0, 0].plot(segment_i[u].values,
                        segment_i[v].values, **line_kw)
        axes[0, 1].plot(segment_i[w].values,
                        segment_i[v].values, **line_kw)
        axes[1, 0].plot(segment_i[u].values,
                        segment_i[w].values, **line_kw)
        if ax_3d is not None:
            ax_3d.plot(segment_i[u].values,
                       segment_i[v].values,
                       zs=segment_i[w].values, **line_kw)

        axes[0, 0].set_ylabel(u'y position (µm)')
        axes[1, 0].set_xlabel(u'x position (µm)')
        axes[1, 0].set_ylabel(u'z position (µm)')

        axes[0, 0].set_ylabel(u'y position (µm)')
        axes[0, 1].set_xlabel(u'z position (µm)')
        if ax_3d is not None:
            ax_3d.set_xlabel(u'x position (µm)')
            ax_3d.set_ylabel(u'y position (µm)')
            ax_3d.set_zlabel(u'z position (µm)')

        return axes, ax_3d


    def plot_stacked_coords(self, coords=('x', 'y', 'z'),
                            text=False, fig=None, **kwargs):
        '''
        Plots stacked graphs with each of the coordinates given in the
        `coords` argument plotted against time.

        Parameters
        ----------
        trajs: a :class:`Trajectories` instance
        coords: a tuple, default ('x', 'y', 'z')
            the coordinates (`trajs` column names) to be ploted
        text: bool, default False
            if True, will append each trajectory segment's label
            at the extremities on the upper most plot
        fig: a matplotlib `Figure`, default `None`
            the figure on which to plot

        Returns
        -------
        axes: a list of :class:`matplotlib.axes.Axes`

        '''
        import matplotlib.pyplot as plt

        if fig is None:
            # Create a figure with 3 graphs verticaly stacked
            fig, axes = plt.subplots(len(coords), 1, sharex=True, figsize=(6, 9))
        else:
            axes = fig.get_axes()

        for coord, ax in zip(coords, axes):
            self.show('t', coord, ax=ax, **kwargs)
            ax.set_ylabel('{} coordinate'.format(coord))
            ax.set_title('')
            ax.set_xlabel('')

        if text:
            for label, segment in self.iter_segments:
                axes[0].text(segment.t.iloc[0],
                             segment[coords[0]].iloc[0], str(label))
                axes[0].text(segment.t.iloc[-1],
                             segment[coords[0]].iloc[-1], str(label))

        axes[-1].set_xlabel('Time')

        fig.tight_layout()
        plt.draw()
        return axes


# Register the trajectories for storing in HDFStore
# as a regular DataFrame
pytables._TYPE_MAP[Trajectories] = 'frame'
