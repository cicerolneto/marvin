#!/usr/bin/env python

import os
import re

import pytest
import numpy as np
from astropy.io import fits
from astropy import wcs

from marvin import config
from marvin.tools.cube import Cube
from marvin.core.core import DotableCaseInsensitive
from marvin.core.exceptions import MarvinError
from marvin.tests import skipIfNoDB, marvin_test_if


class TestCube(object):

    def test_cube_loadfail(self):
        with pytest.raises(AssertionError) as cm:
            Cube()
        assert 'Enter filename, plateifu, or mangaid!' in str(cm.value)

    def test_cube_load_from_local_file_by_filename_success(self, galaxy):
        cube = Cube(filename=galaxy.cubepath)
        assert cube is not None
        assert os.path.realpath(galaxy.cubepath) == cube.filename

    def test_cube_load_from_local_file_by_filename_fail(self):
        with pytest.raises(MarvinError):
            Cube(filename='not_a_filename.fits')

    @skipIfNoDB
    def test_cube_load_from_local_database_success(self, maindb, galaxy):
        """Tests for Cube Load by Database."""
        cube = Cube(mangaid=galaxy.mangaid)
        assert cube is not None
        assert galaxy.mangaid == cube.mangaid
        assert galaxy.plate == cube.plate
        assert galaxy.dec == cube.dec
        assert galaxy.ra == cube.ra

    def _load_from_db_fail(self, params, errMsg, errType=MarvinError):
        with pytest.raises(errType) as cm:
            Cube(**params)
        assert errMsg in str(cm.value)

    @skipIfNoDB
    @pytest.mark.skip('Test fails beacuse local data access switches to ``file`` if db is off.')
    def test_cube_load_from_local_database_nodbconnected(self, galaxy, monkeypatch):
        # need to undo setting the config.db to None so that subsequent tests will pass
        if config.db is not None:
            config.forceDbOff()
            db_on = True
        else:
            db_on = False

        assert config.db is None

        # from marvin.core.core import MarvinToolsClass
        monkeypatch.setattr(Cube, '_getFullPath', lambda x: None)

        params = {'mangaid': galaxy.mangaid, 'mode': 'local'}
        errMsg = 'No db connected'
        self._load_from_db_fail(params, errMsg)

        if db_on:
            config.forceDbOn()

    @skipIfNoDB
    def test_cube_load_from_local_database_noresultsfound(self, maindb):
        params = {'plateifu': '8485-0923', 'mode': 'local'}
        errMsg = 'Could not retrieve cube for plate-ifu {0}: No Results Found'.format(
            params['plateifu'])
        self._load_from_db_fail(params, errMsg, errType=MarvinError)

    @skipIfNoDB
    def test_cube_load_from_local_database_otherexception(self, maindb):
        params = {'plateifu': '84.85-1901', 'mode': 'local'}
        errMsg = 'Could not retrieve cube for plate-ifu {0}: Unknown exception'.format(
            params['plateifu'])
        self._load_from_db_fail(params, errMsg, errType=MarvinError)

    def test_cube_flux_from_local_database(self, galaxy):
        cube = Cube(plateifu=galaxy.plateifu, mode='local')
        flux = cube.flux
        assert cube.data_origin == 'db'

        cubeFlux = fits.getdata(galaxy.cubepath)
        assert np.allclose(flux, cubeFlux)

    @pytest.mark.slow
    def test_cube_flux_from_api(self, galaxy):
        cube = Cube(plateifu=galaxy.plateifu, mode='remote')
        flux = cube.flux
        assert cube.data_origin == 'api'

        cubeFlux = fits.getdata(galaxy.cubepath)
        assert pytest.approx(flux, cubeFlux)

    def test_cube_flux_from_file(self, galaxy):
        cube = Cube(filename=galaxy.cubepath)
        assert cube.data_origin == 'file'
        assert isinstance(cube.flux, np.ndarray)

    def test_cube_remote_drpver_differ_from_global(self, galaxy):

        # This tests requires having the cube for 8485-1901 loaded for both
        # MPL-4 and MPL-5.

        config.setMPL('MPL-5')
        assert config.release == 'MPL-5'

        cube = Cube(plateifu=galaxy.plateifu, mode='remote', release='MPL-4')
        assert cube._drpver == 'v1_5_1'
        assert cube.header['VERSDRP3'].strip() == 'v1_5_0'

    @marvin_test_if(mark='include', data_origin=['db'])
    def test_cube_redshift_db(self, galaxy):
        cube = Cube(plateifu=galaxy.plateifu, mode='local')
        assert pytest.approx(cube.nsa.z, galaxy.redshift)

    @marvin_test_if(mark='include', data_origin=['file'])
    @marvin_test_if(mark='include', galaxy=dict(release=['MPL-4']))
    def test_cube_redshift_file_MPL4(self, galaxy):        
        cube = Cube(filename=galaxy.cubepath)
        assert pytest.approx(cube.nsa.redshift, galaxy.redshift)
    
    @marvin_test_if(mark='include', data_origin=['file'])
    @marvin_test_if(mark='include', galaxy=dict(release=['MPL-5']))
    def test_cube_redshift_file_MPL5(self, galaxy):
        cube = Cube(filename=galaxy.cubepath)
        assert pytest.approx(cube.nsa.z, galaxy.redshift)

    @marvin_test_if(mark='include', data_origin=['api'])
    def test_cube_redshift_api(self, galaxy):
        cube = Cube(plateifu=galaxy.plateifu, mode='remote')
        assert pytest.approx(cube.nsa.z, galaxy.redshift)

    @pytest.mark.parametrize('nsa_source',
                             ['auto', 'nsa', 'drpall'])
    @marvin_test_if(mark='include', data_origin=['db', 'api'])
    def test_nsa_redshift_db_api(self, galaxy, nsa_source, mode):    
        cube = Cube(plateifu=galaxy.plateifu, nsa_source=nsa_source, mode=mode)
        assert cube.nsa_source == nsa_source
        # assert cube.nsa['nsaid'] == galaxy.nsaid
        assert isinstance(cube.nsa, DotableCaseInsensitive)
        if mode == 'drpall':
            assert 'profmean_ivar' not in cube.nsa.keys()
        assert 'zdist' in cube.nsa.keys()
        assert pytest.approx(cube.nsa['zdist'], galaxy.redshift)
        assert pytest.approx(cube.nsa['sersic_n'], galaxy.nsa_data['sersic_n'])

    @pytest.mark.parametrize('nsa_source',
                             ['auto', 'nsa', 'drpall'])
    @marvin_test_if(mark='include', mode=['local', 'auto'])
    @marvin_test_if(mark='include', data_origin=['file'])
    def test_nsa_redshift_file(self, galaxy, nsa_source, mode):    
        cube = Cube(filename=galaxy.cubepath, nsa_source=nsa_source, mode=mode)
        assert cube.nsa_source == nsa_source
        # assert cube.nsa['nsaid'] == galaxy.nsaid
        assert isinstance(cube.nsa, DotableCaseInsensitive)
        if mode == 'drpall':
            assert 'profmean_ivar' not in cube.nsa.keys()
        assert 'zdist' in cube.nsa.keys()
        assert pytest.approx(cube.nsa['zdist'], galaxy.redshift)
        assert pytest.approx(cube.nsa['sersic_n'], galaxy.nsa_data['sersic_n'])


    def test_release(self, galaxy):
        cube = Cube(plateifu=galaxy.plateifu)
        assert cube.release == galaxy.release

    def test_set_release_fails(self, galaxy):
        cube = Cube(plateifu=galaxy.plateifu)
        with pytest.raises(MarvinError) as ee:
            cube.release = 'a'
            assert 'the release cannot be changed' in str(ee.exception)

    def test_load_filename_does_not_exist(self):
        """Tries to load a file that does not exist, in auto mode."""
        config.mode = 'auto'
        with pytest.raises(MarvinError) as ee:
            Cube(filename='hola.fits')

        assert re.match(r'input file .+hola.fits not found', str(ee.value)) is not None

    def test_load_filename_remote(self):
        """Tries to load a filename in remote mode and fails."""
        config.mode = 'remote'
        with pytest.raises(MarvinError) as ee:
            Cube(filename='hola.fits')

        assert 'filename not allowed in remote mode' in str(ee.value)


class TestGetSpaxel(object):

    def _dropNones(self, **kwargs):
        for k, v in list(kwargs.items()):
            if v is None:
                del kwargs[k]
        return kwargs

    @pytest.mark.parametrize('x, y, ra, dec, excType, message',
        [(1, None, 1, None, AssertionError, 'Either use (x, y) or (ra, dec)'),
         (1, None, 1, 1, AssertionError, 'Either use (x, y) or (ra, dec)'),
         (1, None, None, None, AssertionError, 'Specify both x and y'),
         (None, 1, None, None, AssertionError, 'Specify both x and y'),
         (None, None, 1, None, AssertionError, 'Specify both ra and dec'),
         (None, None, None, 1, AssertionError, 'Specify both ra and dec'),
         (None, None, None, None, ValueError, 'You need to specify either (x, y) or (ra, dec)'),
         (-50, 1, None, None, MarvinError, 'some indices are out of limits'),
         (50, 1, None, None, MarvinError, 'some indices are out of limits'),
         (1, -50, None, None, MarvinError, 'some indices are out of limits'),
         (1, 50, None, None, MarvinError, 'some indices are out of limits'),
         (None, None, 1., 1., MarvinError, 'some indices are out of limits'),
         (None, None, 100, 60, MarvinError, 'some indices are out of limits'),
         (None, None, 232.546383, 1., MarvinError, 'some indices are out of limits'),
         (None, None, 1., 48.6883954, MarvinError, 'some indices are out of limits')],
        ids=['x-ra', 'x-ra-dec', 'x', 'y', 'ra', 'dec', 'no-inputs', '-50-1', '50-1', '1--50',
             '1-50', '1-1', '100-60', '232.5-1', '1-48.6'])
    def test_getSpaxel_inputs(self, galaxy, x, y, ra, dec, excType, message):
        """Tests exceptions when getSpaxel gets inappropriate inputs."""
        kwargs = self._dropNones(x=x, y=y, ra=ra, dec=dec)

        with pytest.raises(excType) as ee:
            cube = Cube(filename=galaxy.cubepath)
            cube.getSpaxel(**kwargs)

        assert message in str(ee.value)

    @pytest.mark.parametrize('x, y, ra, dec, xyorig, idx, mpl4, mpl5',
        [(10, 5, None, None, None, 10, -0.062497504, -0.063987106),
         (10, 5, None, None, 'center', 10, -0.062497504, -0.063987106),
         (10, 5, None, None, 'lower', 3000, 0.017929086, 0.017640527),
         (0, 0, None, None, None, 3000, 1.0493046, 1.0505702),
         (0, 0, None, None, 'lower', 3000, 0., 0.),
         (None, None, 232.5443, 48.6899, None, 3000, 0.62007582, 0.6171338),
         (None, None, 232.544279, 48.6899232, None, 3000, 0.62007582, 0.6171338),
         ([10, 0], [5, 0], None, None, 'lower', 3000, [0.017929086, 0.], [0.017640527, 0.]),
         (None, None, [232.546173, 232.548277], [48.6885343, 48.6878398], 'lower', 3000,
          [0.017929086, 0.0], [0.017640527, 0.]),
         (None, None, 232.54, 48.69, None, 3000, MarvinError, MarvinError),
         (None, None, 233, 49, None, 3000, MarvinError, MarvinError)
         ],
        ids=['xy', 'xycenter', 'xylower', 'x0y0', 'x0y0lower', 'radec-partial', 'radec-full',
             'xyarray', 'radecarray', 'radec-fail-twosigfig', 'radec-fail-int'])
    @pytest.mark.parametrize('data_origin', ['db', 'file', 'api'])
    def test_getSpaxel_flux(self, request, galaxy, data_origin, x, y, ra, dec, xyorig, idx, mpl4,
                            mpl5):
        cube = request.getfixturevalue('cube_' + data_origin)

        kwargs = self._dropNones(x=x, y=y, ra=ra, dec=dec, xyorig=xyorig)
        mpls = {'MPL-4': mpl4, 'MPL-5': mpl5}
        expected = mpls[config.release]

        if expected is MarvinError:
            with pytest.raises(MarvinError) as cm:
                actual = cube.getSpaxel(**kwargs).spectrum.flux[idx]
            assert 'some indices are out of limits.' in str(cm.value)
        else:
            spaxels = cube.getSpaxel(**kwargs)
            spaxels = spaxels if isinstance(spaxels, list) else [spaxels]
            actual = [getattr(spax.spectrum, 'flux')[idx] for spax in spaxels]
            expected = expected if isinstance(expected, list) else [expected]
            assert pytest.approx(actual, expected)

    @pytest.mark.parametrize('monkeyconfig',
                             [('sasurl', 'http://www.averywrongurl.com')],
                             ids=['wrongurl'], indirect=True)
    def test_getSpaxel_remote_fail_badresponse(self, monkeyconfig):
        assert config.urlmap is not None

        with pytest.raises(MarvinError) as cm:
            Cube(mangaid='1-209232', mode='remote')

        assert 'Failed to establish a new connection' in str(cm.value)

    def test_getSpaxel_remote_drpver_differ_from_global(self, galaxy):
        config.setMPL('MPL-5')
        assert config.release == 'MPL-5'

        cube = Cube(plateifu=galaxy.plateifu, mode='remote', release='MPL-4')
        expected = 0.62007582

        spectrum = cube.getSpaxel(ra=232.544279, dec=48.6899232).spectrum
        assert pytest.approx(spectrum.flux[3000], expected)

    def test_getspaxel_matches_file_db_remote(self, galaxy):

        cube_file = Cube(filename=galaxy.cubepath)
        cube_db = Cube(plateifu=galaxy.plateifu)
        cube_api = Cube(plateifu=galaxy.plateifu, mode='remote')

        assert cube_file.data_origin == 'file'
        assert cube_db.data_origin == 'db'
        assert cube_api.data_origin == 'api'

        xx = galaxy.spaxel['x']
        yy = galaxy.spaxel['y']
        spec_idx = galaxy.spaxel['specidx']
        flux = galaxy.spaxel['flux']
        ivar = galaxy.spaxel['ivar']
        mask = galaxy.spaxel['mask']

        spaxel_slice_file = cube_file[yy, xx]
        spaxel_slice_db = cube_db[yy, xx]
        spaxel_slice_api = cube_api[yy, xx]

        assert pytest.approx(spaxel_slice_file.spectrum.flux[spec_idx], flux)
        assert pytest.approx(spaxel_slice_db.spectrum.flux[spec_idx], flux)
        assert pytest.approx(spaxel_slice_api.spectrum.flux[spec_idx], flux)

        assert pytest.approx(spaxel_slice_file.spectrum.ivar[spec_idx], ivar)
        assert pytest.approx(spaxel_slice_db.spectrum.ivar[spec_idx], ivar)
        assert pytest.approx(spaxel_slice_api.spectrum.ivar[spec_idx], ivar)

        assert pytest.approx(spaxel_slice_file.spectrum.mask[spec_idx], mask)
        assert pytest.approx(spaxel_slice_db.spectrum.mask[spec_idx], mask)
        assert pytest.approx(spaxel_slice_api.spectrum.mask[spec_idx], mask)

        xx_cen = galaxy.spaxel['x_cen']
        yy_cen = galaxy.spaxel['y_cen']

        spaxel_getspaxel_file = cube_file.getSpaxel(x=xx_cen, y=yy_cen)
        spaxel_getspaxel_db = cube_db.getSpaxel(x=xx_cen, y=yy_cen)
        spaxel_getspaxel_api = cube_api.getSpaxel(x=xx_cen, y=yy_cen)

        assert pytest.approx(spaxel_getspaxel_file.spectrum.flux[spec_idx], flux)
        assert pytest.approx(spaxel_getspaxel_db.spectrum.flux[spec_idx], flux)
        assert pytest.approx(spaxel_getspaxel_api.spectrum.flux[spec_idx], flux)

        assert pytest.approx(spaxel_getspaxel_file.spectrum.ivar[spec_idx], ivar)
        assert pytest.approx(spaxel_getspaxel_db.spectrum.ivar[spec_idx], ivar)
        assert pytest.approx(spaxel_getspaxel_api.spectrum.ivar[spec_idx], ivar)

        assert pytest.approx(spaxel_getspaxel_file.spectrum.mask[spec_idx], mask)
        assert pytest.approx(spaxel_getspaxel_db.spectrum.mask[spec_idx], mask)
        assert pytest.approx(spaxel_getspaxel_api.spectrum.mask[spec_idx], mask)


class TestWCS(object):

    def test_wcs_file(self, galaxy):
        cube = Cube(filename=galaxy.cubepath)
        assert isinstance(cube.wcs, wcs.WCS)
        assert pytest.approx(cube.wcs.wcs.cd[1, 1], 0.000138889)

    def test_wcs_db(self, galaxy):
        cube = Cube(plateifu=galaxy.plateifu)
        assert isinstance(cube.wcs, wcs.WCS)
        assert pytest.approx(cube.wcs.wcs.cd[1, 1], 0.000138889)

    def test_wcs_api(self, galaxy):
        cube = Cube(plateifu=galaxy.plateifu, mode='remote')
        assert isinstance(cube.wcs, wcs.WCS)
        assert pytest.approx(cube.wcs.wcs.pc[1, 1], 0.000138889)


class TestPickling(object):

    def test_pickling_file(self, tmpfiles, galaxy):
        cube = Cube(filename=galaxy.cubepath)
        assert cube.data_origin == 'file'
        assert isinstance(cube, Cube)
        assert cube.data is not None

        assert not os.path.isfile(galaxy.cubepath[0:-7] + 'mpf')

        path = cube.save()
        tmpfiles.append(path)

        assert os.path.exists(path)
        assert cube.data is not None

        cube = None
        assert cube is None

        cube_restored = Cube.restore(path)
        assert cube_restored.data_origin == 'file'
        assert isinstance(cube_restored, Cube)
        assert cube_restored.data is not None

    def test_pickling_file_custom_path(self, tmpfiles, galaxy):
        cube = Cube(filename=galaxy.cubepath)
        assert cube.data_origin == 'file'
        assert isinstance(cube, Cube)
        assert cube.data is not None

        test_path = '~/test.mpf'
        assert not os.path.isfile(test_path)

        path = cube.save(path=test_path)
        tmpfiles.append(path)

        assert os.path.exists(path)
        assert path == os.path.realpath(os.path.expanduser(test_path))

        cube_restored = Cube.restore(path, delete=True)
        assert cube_restored.data_origin == 'file'
        assert isinstance(cube_restored, Cube)
        assert cube_restored.data is not None

        assert not os.path.exists(path)

    def test_pickling_db(self, galaxy):
        cube = Cube(plateifu=galaxy.plateifu)
        assert cube.data_origin == 'db'

        with pytest.raises(MarvinError) as cm:
            cube.save()

        assert 'objects with data_origin=\'db\' cannot be saved.' in str(cm.value)

    def test_pickling_api(self, tmpfiles, galaxy):
        cube = Cube(plateifu=galaxy.plateifu, mode='remote')
        assert cube.data_origin == 'api'
        assert isinstance(cube, Cube)
        assert cube.data is None

        path = cube.save()
        tmpfiles.append(path)

        assert os.path.exists(path)
        assert os.path.realpath(path) == os.path.realpath(galaxy.cubepath[0:-7] + 'mpf')

        cube = None
        assert cube is None

        cube_restored = Cube.restore(path)
        assert cube_restored.data_origin == 'api'
        assert isinstance(cube_restored, Cube)
        assert cube_restored.data is None
