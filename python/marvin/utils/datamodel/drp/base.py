#!/usr/bin/env python
# encoding: utf-8
#
# @Author: Brian Cherinka, José Sánchez-Gallego, Brett Andrews
# @Date: Oct 25, 2017
# @Filename: base.py
# @License: BSD 3-Clause
# @Copyright: Brian Cherinka, José Sánchez-Gallego, Brett Andrews


from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import copy as copy_mod

import astropy.table as table
from astropy import units as u

from .. import DataModelList
from ...general.structs import FuzzyList


class DRPDataModel(object):
    """A class representing a DAP datamodel, with bintypes, templates, properties, etc."""

    def __init__(self, release, datacubes=[], spectra=[], aliases=[]):

        self.release = release
        self.aliases = aliases

        self.datacubes = DataCubeList(datacubes, parent=self)
        self.spectra = SpectrumList(spectra, parent=self)

    def __repr__(self):

        return ('<DRPDataModel release={0!r}, n_datacubes={1}>'
                .format(self.release, len(self.datacubes)))

    def copy(self):
        """Returns a copy of the datamodel."""

        return copy_mod.deepcopy(self)

    def __eq__(self, value):
        """Uses fuzzywuzzy to return the closest property match."""

        datacube_names = [datacube.name for datacube in self.datacubes]
        spectrum_names = [spectrum.name for spectrum in self.spectra]

        if value in datacube_names:
            return self.datacubes[datacube_names.index(value)]
        elif value in spectrum_names:
            return self.spectra[spectrum_names.index(value)]

        try:
            datacube_best_match = self.datacubes[value]
        except ValueError:
            datacube_best_match = None

        try:
            spectrum_best_match = self.spectra[value]
        except ValueError:
            spectrum_best_match = None

        if ((datacube_best_match is None and spectrum_best_match is None) or
                (datacube_best_match is not None and spectrum_best_match is not None)):
            raise ValueError('too ambiguous input {!r}'.format(value))
        elif datacube_best_match is not None:
            return datacube_best_match
        elif spectrum_best_match is not None:
            return spectrum_best_match

    def __contains__(self, value):

        try:
            match = self.__eq__(value)
            if match is None:
                return False
            else:
                return True
        except ValueError:
            return False

    def __getitem__(self, value):
        return self == value


class DRPDataModelList(DataModelList):
    """A dictionary of DRP datamodels."""

    base = {'DRPDataModel': DRPDataModel}


class DataCubeList(FuzzyList):
    """Creates a list containing models and their representation."""

    def __init__(self, the_list, parent=None):

        self.parent = parent

        super(DataCubeList, self).__init__([], mapper=lambda xx: xx.full())

        for item in the_list:
            self.append(item, copy=True)

    def append(self, value, copy=True):
        """Appends with copy."""

        append_obj = value if copy is False else copy_mod.deepcopy(value)
        append_obj.parent = self.parent

        if isinstance(append_obj, DataCube):
            super(DataCubeList, self).append(append_obj)
        else:
            raise ValueError('invalid datacube of type {!r}'.format(type(append_obj)))

    def to_table(self, pprint=False, description=False, max_width=1000):
        """Returns an astropy table with all the datacubes in this datamodel.

        Parameters:
            pprint (bool):
                Whether the table should be printed to screen using astropy's
                table pretty print.
            description (bool):
                If ``True``, an extra column with the description of the
                datacube will be added.
            max_width (int or None):
                A keyword to pass to ``astropy.table.Table.pprint()`` with the
                maximum width of the table, in characters.

        Returns:
            result (``astropy.table.Table``):
                If ``pprint=False``, returns an astropy table containing
                the name of the datacube, whether it has ``ivar`` or
                ``mask``, the units, and a description (if
                ``description=True``)..

        """

        datacube_table = table.Table(
            None, names=['name', 'ivar', 'mask', 'unit', 'description'],
            dtype=['S20', bool, bool, 'S20', 'S500'])

        if self.parent:
            datacube_table.meta['release'] = self.parent.release

        for datacube in self:
            unit = datacube.unit.to_string()

            datacube_table.add_row((datacube.name,
                                   datacube.extension_ivar is not None,
                                   datacube.extension_mask is not None,
                                   unit,
                                   datacube.description))

        if not description:
            datacube_table.remove_column('description')

        if pprint:
            datacube_table.pprint(max_width=max_width, max_lines=1e6)
            return

        return datacube_table


class DataCube(object):
    """Represents a extension in the DRP logcube file.

    Parameters:
        name (str):
            The datacube name. This is the internal name that Marvin will use
            for this datacube. It is different from the ``extension_name``
            parameter, which must be identical to the extension name of the
            datacube in the logcube file.
        extension_name (str):
            The FITS extension containing this datacube.
        extension_wave (str):
            The FITS extension containing the wavelength for this datacube.
        extension_ivar (str or None):
            The extension that contains the inverse variance associated with
            this datacube, if any.
        extension_mask (str or None):
            The extension that contains the mask associated with this
            datacube, if any.
        unit (astropy unit or None):
            The unit for this datacube.
        scale (float):
            The scaling factor for the values of the datacube.
        formats (dict):
            A dictionary with formats that can be used to represent the
            datacube. Default ones are ``latex`` and ``string``.
        description (str):
            A description for the datacube.

    """

    def __init__(self, name, extension_name, extension_wave=None,
                 extension_ivar=None, extension_mask=None,
                 unit=u.dimensionless_unscaled, scale=1, formats={},
                 description=''):

        self.name = name
        self.extension_name = extension_name
        self.extension_wave = extension_wave
        self.extension_ivar = extension_ivar
        self.extension_mask = extension_mask
        self.unit = unit
        self.scale = scale
        self.formats = formats
        self.description = description

    def set_parent(self, parent):
        """Sets parent."""

        assert isinstance(parent, DataCube), 'parent must be a DataCube'

        self.parent = parent

    def full(self):
        """Returns the name string."""

        return self.extension_name.lower()

    def db_column(self, ext=None):
        """Returns the name of the DB column containing this datacube."""

        assert ext is None or ext in ['ivar', 'mask'], 'invalid extension'

        if ext is None:
            return self.full()

        if ext == 'ivar':
            assert self.extension_ivar is not None, \
                'no ivar for datacube {0!r}'.format(self.full())
            return self.extension_ivar.lower()

        if ext == 'mask':
            assert self.extension_mask is not None, \
                'no mask for datacube {0!r}'.format(self.full())
            return self.extension_mask.lower()

    def __repr__(self):

        return '<DataCube {!r}, release={!r}, unit={!r}>'.format(
            self.name, self.parent.release if self.parent else None, self.unit.to_string())

    def __str__(self):

        return self.full()

    def to_string(self, mode='string'):
        """Return a string representation of the datacube."""

        if mode == 'latex':

            if mode in self.formats:
                latex = self.formats[mode]
            else:
                latex = self.to_string()

            return latex

        else:

            if mode in self.formats:
                string = self.formats[mode]
            else:
                string = self.name

            return string


class SpectrumList(FuzzyList):
    """Creates a list containing spectra and their representation."""

    def __init__(self, the_list, parent=None):

        self.parent = parent

        super(SpectrumList, self).__init__([], mapper=lambda xx: xx.full())

        for item in the_list:
            self.append(item, copy=True)

    def append(self, value, copy=True):
        """Appends with copy."""

        append_obj = value if copy is False else copy_mod.deepcopy(value)
        append_obj.parent = self.parent

        if isinstance(append_obj, Spectrum):
            super(SpectrumList, self).append(append_obj)
        else:
            raise ValueError('invalid spectrum of type {!r}'.format(type(append_obj)))

    def to_table(self, pprint=False, description=False, max_width=1000):
        """Returns an astropy table with all the spectra in this datamodel.

        Parameters:
            pprint (bool):
                Whether the table should be printed to screen using astropy's
                table pretty print.
            description (bool):
                If ``True``, an extra column with the description of the
                spectrum will be added.
            max_width (int or None):
                A keyword to pass to ``astropy.table.Table.pprint()`` with the
                maximum width of the table, in characters.

        Returns:
            result (``astropy.table.Table``):
                If ``pprint=False``, returns an astropy table containing
                the name of the spectrum, whether it has ``ivar`` or
                ``mask``, the units, and a description (if
                ``description=True``)..

        """

        spectrum_table = table.Table(
            None, names=['name', 'ivar', 'mask', 'unit', 'description'],
            dtype=['S20', bool, bool, 'S20', 'S500'])

        if self.parent:
            spectrum_table.meta['release'] = self.parent.release

        for spectrum in self:
            unit = spectrum.unit.to_string()

            spectrum_table.add_row((spectrum.name,
                                    spectrum.extension_ivar is not None,
                                    spectrum.extension_mask is not None,
                                    unit,
                                    spectrum.description))

        if not description:
            spectrum_table.remove_column('description')

        if pprint:
            spectrum_table.pprint(max_width=max_width, max_lines=1e6)
            return

        return spectrum_table


class Spectrum(object):
    """Represents a extension in the DRP logcube file.

    Parameters:
        name (str):
            The spectrum name. This is the internal name that Marvin will use
            for this spectrum. It is different from the ``extension_name``
            parameter, which must be identical to the extension name of the
            spectrum in the logcube file.
        extension_name (str):
            The FITS extension containing this spectrum.
        extension_wave (str):
            The FITS extension containing the wavelength for this spectrum.
        extension_std (str):
            The FITS extension containing the standard deviation for this
            spectrum.
        unit (astropy unit or None):
            The unit for this spectrum.
        scale (float):
            The scaling factor for the values of the spectrum.
        formats (dict):
            A dictionary with formats that can be used to represent the
            spectrum. Default ones are ``latex`` and ``string``.
        description (str):
            A description for the spectrum.

    """

    def __init__(self, name, extension_name, extension_wave=None, extension_std=None,
                 unit=u.dimensionless_unscaled, scale=1, formats={},
                 description=''):

        self.name = name
        self.extension_name = extension_name
        self.extension_wave = extension_wave
        self.extension_std = extension_std
        self.unit = unit
        self.scale = scale
        self.formats = formats
        self.description = description

    def set_parent(self, parent):
        """Sets parent."""

        assert isinstance(parent, Spectrum), 'parent must be a Spectrum'

        self.parent = parent

    def full(self):
        """Returns the name string."""

        return self.extension_name.lower()

    def db_column(self, ext=None):
        """Returns the name of the DB column containing this datacube."""

        if ext is None:
            return self.extension_name.lower()
        elif ext == 'std':
            return self.extension_std.lower()
        else:
            raise ValueError('invalid extension.')

    def __repr__(self):

        return '<Spectrum {!r}, release={!r}, unit={!r}>'.format(
            self.name, self.parent.release if self.parent else None, self.unit.to_string())

    def __str__(self):

        return self.full()

    def to_string(self, mode='string'):
        """Return a string representation of the spectrum."""

        if mode == 'latex':

            if mode in self.formats:
                latex = self.formats[mode]
            else:
                latex = self.to_string()

            return latex

        else:

            if mode in self.formats:
                string = self.formats[mode]
            else:
                string = self.name

            return string
