# -*- coding: utf-8 -*-

from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import
from __future__ import print_function


import logging
import sys
import os
import tempfile
import shutil

if sys.version_info[0] > 2:
    from collections import UserDict
else:
    from UserDict import UserDict

import pandas as pd

log = logging.getLogger(__name__)

from . import validate_metadata

__all__ = []


class ObjectsIO(object):
    """
    Manipulate and pass along data issued from detected
    objects.

    Parameters
    ----------
    metadata : dict
        Metadata related to an image or images list.
    store_path : str
        Path to HDF5 file where metadata and objects are stored.
    base_dir : str
        Root directory (join to find `store_path`)

    """

    def __init__(self, metadata=None,
                 store_path=None,
                 base_dir=None,
                 minimum_metadata_keys=[]):

        if metadata is not None:
            validate_metadata(metadata, keys=minimum_metadata_keys)

        if store_path is None:
            store_name = metadata['FileName'].split(os.path.sep)[-1]
            store_name = store_name.split('.')[0] + '.h5'
            store_path = os.path.join(os.path.dirname(metadata['FileName']),
                                      store_name)
        self.base_dir = base_dir
        if base_dir is None:
            self.store_path = store_path
            if metadata is None:
                self.metadata = OIOMetadata(self['metadata'], self)
            else:
                self.metadata = OIOMetadata(metadata, self)
            self.image_path = self.metadata['FileName']
        else:
            self.store_path = os.path.join(base_dir, store_path)
            if metadata is None:
                self.metadata = OIOMetadata(self['metadata'], self)
            else:
                self.metadata = OIOMetadata(metadata, self)
            self.image_path = os.path.join(base_dir, self.metadata['FileName'])

    @classmethod
    def from_stackio(cls, stackio):
        """Loads metadata from :class:`sktracker.io.stackio`

        Parameters
        ----------
        stackio : :class:`sktracker.io.StackIO`
        """
        return cls(metadata=stackio.metadata)

    def __getitem__(self, name):
        """Get an object from HDF5 file.

        Parameters
        ----------
        name : str
            Name of the object. Will be used when reading HDF5 file

        """
        with pd.get_store(self.store_path) as store:
            obj = store[name]

        if isinstance(obj, pd.Series):
            return obj.to_dict()
        else:
            return obj

    def __setitem__(self, name, obj):
        """Adds an object to HDF5 file. See https://github.com/pydata/pandas/issues/2132 for the
        reason a new store is created.

        Parameters
        ----------
        obj : object
            :class:`pandas.DataFrame`, :class:`pandas.Series` or dict
        name : str
            Name of the object. Will be used when reading HDF5 file

        """
        _, fname = tempfile.mkstemp()

        with pd.get_store(self.store_path) as store:
            new_store = store.copy(fname)

        if isinstance(obj, pd.DataFrame) or isinstance(obj, pd.Series):
            # new_store.put(name, obj, format='t')
            new_store[name] = obj
        elif isinstance(obj, dict) or isinstance(obj, UserDict):
            new_store[name] = _serialize(obj)

        new_store.close()

        shutil.copy(fname, self.store_path)

    def __delitem__(self, name):
        """
        """
        with pd.get_store(self.store_path) as store:
            store.remove('name')

    def keys(self):
        """Return list of objects in HDF5 file.
        """

        objs = []
        with pd.get_store(self.store_path) as store:
            objs = store.keys()
        return objs

    @classmethod
    def from_h5(cls, store_path, base_dir=None, minimum_metadata_keys=[]):
        """Load ObjectsIO from HDF5 file.

        Parameters
        ----------
        store_path : str
            HDF5 file path.
        base_dir : str
            Root directory

        """

        if base_dir:
            full_store_path = os.path.join(base_dir, store_path)
        else:
            full_store_path = store_path

        with pd.get_store(full_store_path) as store:
            metadata_serie = store['metadata']

        metadata = metadata_serie.to_dict()

        return cls(metadata=metadata,
                   store_path=store_path,
                   base_dir=base_dir,
                   minimum_metadata_keys=minimum_metadata_keys)


def _serialize(attr):
    ''' Creates a pandas series from a dictionnary'''
    return pd.Series(attr)


class OIOMetadata(UserDict):
    '''
    A subclass of UserDict with a modified `__setitem__`, such that
    any modification to the metadata is copied to the `h5` file
    '''
    def __init__(self, metadata_dict, objectsio):
        self.objectsio = objectsio
        UserDict.__init__(self, metadata_dict)
        self.objectsio['metadata'] = self.data

    def __setitem__(self, key, value):

        self.data[key] = value
        self.objectsio['metadata'] = self.data