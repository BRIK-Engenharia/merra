#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

# Copyright (c) 2014,Vienna University of Technology, Department of Geodesy and Geoinformation
# All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#   * Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#    * Neither the name of the Vienna University of Technology, Department of
#      Geodesy and Geoinformation nor the names of its contributors may be
#      used to endorse or promote products derived from this software without
#      specific prior written permission.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL VIENNA UNIVERSITY OF TECHNOLOGY,
# DEPARTMENT OF GEODESY AND GEOINFORMATION BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
Created on 02-02-2017

@author: fzaussin
@email: felix.zaussinger@geo.tuwien.ac.at
"""

import os
import numpy as np

import monthdelta
from datetime import timedelta
from netCDF4 import Dataset
from merra.grid import MERRACellgrid

import pygeogrids
from pygeobase.io_base import ImageBase, MultiTemporalImageBase
from pygeobase.object_base import Image
from pygeogrids.netcdf import load_grid
from pynetcf.time_series import GriddedNcOrthoMultiTs


class MERRA_Img_m(ImageBase):
    """
    Class for reading one MERRA-2 nc file in monthly resolution.

    Parameters
    ----------
    filename: string
        filename of the MERRA2 nc file
    mode: string, optional
        mode of opening the file, only 'r' is implemented at the moment
    parameter : string or list, optional
        one or list of parameters to read, see MERRA2 documentation for more information
        Default : 'SFMC'
    array_1D: boolean, optional
        if set then the data is read into 1D arrays. Needed for some legacy code.
    """
    def __init__(self, filename, mode='r', parameter='SFMC', array_1D=False):
        super(MERRA_Img_m, self).__init__(filename, mode=mode)

        if not isinstance(parameter, list):
            parameter = [parameter]
        self.parameters = parameter
        self.fill_values = np.repeat(1e15, 361 * 576)
        self.grid = MERRACellgrid()
        self.array_1D = array_1D
        self.filename = filename

    def open_file(self):
        """
        Try to open dataset.

        Returns
        -------
        dataset : netCDF4.Dataset object
        """
        try:
            dataset = Dataset(self.filename)
            # data model and chunksize changed from 2015/06 to 2015/07 of monthly data
            if dataset.data_model in ('NETCDF4', 'NETCDF4_CLASSIC'):
                print("Successfully opened file '{}'.\n".format(dataset.Filename))
                return dataset
        except IOError as e:
            print(e)
            print(" ".join([self.filename, "can not be opened."]))
            raise e

    def read(self, timestamp=None):
        """
        Reads single image for given timestamp.

        Parameters
        ----------
        timestamp : datetime.datetime
            exact timestamp of the image

        Returns
        -------
        Image : object
            pygeobase.object_base.Image object
        """
        print("Reading file: {}".format(self.filename))

        # return selected parameters and metadata for an image
        return_img = {}
        return_metadata = {}

        # open dataset
        dataset = self.open_file()

        # build parameter list
        param_names = []
        for param in self.parameters:
            param_names.append(param)

        # Iterate over all parameters in nc file
        for parameter, variable in dataset.variables.items():
            # Only process selected parameters
            if parameter in param_names:
                param_metadata = {}

                # Iterate over all attributes of the selected parameters
                for attr_name in variable.ncattrs():
                    # Only extract metadata of the attributes in the list
                    if attr_name in ['long_name', 'units']:
                        param_metadata.update(
                            {attr_name: getattr(variable, attr_name)})

                param_data = dataset.variables[parameter][:]

                # SFMC is returned as nd-array in place of a masked array
                # type handling

                if not isinstance(param_data, np.ma.masked_array):
                    print("Parameter {} is of type {}. Should be {}.").format(
                        parameter, type(param_data), np.ma.masked_array)
                    # flatten nd-array
                    param_data = param_data.flatten()
                else:

                    # masked array to 1d nd-array
                    param_data = np.ma.getdata(param_data).flatten()

                # update data and metadata dicts depending on declared
                # parameters
                # gpis = 207936
                return_img.update(
                    {parameter: param_data[self.grid.activegpis]})
                return_metadata.update({parameter: param_metadata})

                # Check for corrupt files
                try:
                    return_img[parameter]
                except KeyError:
                    path, file_name = os.path.split(self.filename)
                    print('%s in %s is corrupt - filling image with NaN values' % (parameter, file_name))
                    return_img[parameter] = np.empty(
                        self.grid.n_gpi).fill(np.nan)
                    return_metadata['corrupt_parameters'].append()

        if self.array_1D:
            return Image(self.grid.activearrlon,
                         self.grid.activearrlat,
                         return_img,
                         return_metadata,
                         timestamp)
        else:
            # iterate trough return_img dict and reshape nd-array to 361 x 576
            # matrix
            for key in return_img:
                print(key)
                return_img[key] = np.flipud(
                    return_img[key].reshape((361, 576)))

            # return Image object for called parameters
            return Image(np.flipud(self.grid.activearrlon.reshape((361, 576))),
                         np.flipud(self.grid.activearrlat.reshape((361, 576))),
                         return_img,
                         return_metadata,
                         timestamp)

    def write(self, image, **kwargs):
        """
        Write data to an image file.

        Parameters
        ----------
        image : object
            pygeobase.object_base.Image object
        """
        raise NotImplementedError()
        pass

    def flush(self):
        """
        Flush data.
        """
        pass

    def close(self):
        """
        Close file.
        """
        pass


class MERRA_Img(ImageBase):
    """
    Class for reading one MERRA-2 nc file in 1h temporal sampling. One file
    represents an image stack of shape (361, 576, 24).

    Parameters
    ----------
    filename: string
        filename of the MERRA2 nc file
    mode: string, optional
        mode of opening the file, only 'r' is implemented at the moment
    parameter : string or list, optional
        one or list of parameters to read, see MERRA2 documentation for more information
        Default : 'SFMC'
    array_1D: boolean, optional
        if set then the data is read into 1D arrays. Needed for some legacy code.
    """

    def __init__(self, filename, mode='r', parameter='SFMC', array_1D=False):
        super(MERRA_Img, self).__init__(filename, mode=mode)

        if not isinstance(parameter, list):
            parameter = [parameter]
        self.parameters = parameter
        self.fill_values = np.repeat(1e15, 361 * 576)
        self.grid = MERRACellgrid()
        self.array_1D = array_1D
        self.filename = filename

    def open_file(self):
        """
        Try to open dataset.

        Returns
        -------
        dataset : netCDF4.Dataset object
        """
        try:
            dataset = Dataset(self.filename)
            if dataset.data_model in ('NETCDF4', 'NETCDF4_CLASSIC'):
                print("Successfully opened file '{}'.\n".format(dataset.Filename))
                return dataset
        except IOError as e:
            print(e)
            print(" ".join([self.filename, "can not be opened."]))
            raise e

    def read(self, timestamp):
        """
        Reads single hourly image for given timestamp.

        Parameters
        ----------
        timestamp : datetime.datetime
            exact timestamp of the image

        Returns
        -------
        Image : object
            pygeobase.object_base.Image object
        """
        print("Reading file: {}".format(self.filename))

        # return selected parameters and metadata for an image
        return_img = {}
        return_metadata = {}

        # open dataset
        dataset = self.open_file()

        # build parameter list
        param_names = []
        for param in self.parameters:
            param_names.append(param)

        # Iterate over all parameters in nc file
        for parameter, variable in dataset.variables.items():
            # Only process selected parameters
            if parameter in param_names:
                param_metadata = {}

                # Iterate over all attributes of the selected parameters
                for attr_name in variable.ncattrs():
                    # Only extract metadata of the attributes in the list
                    if attr_name in ['long_name', 'units']:
                        param_metadata.update(
                            {attr_name: getattr(variable, attr_name)})

                # retrieve data as 3D-array
                param_stack = dataset.variables[parameter][:]

                # only retrieve the image at the given timestamp
                param_data = param_stack[timestamp.hour]

                if not isinstance(param_data, np.ma.masked_array):
                    param_data = param_data.flatten()
                else:
                    # masked array to 1d nd-array
                    param_data = np.ma.getdata(param_data).flatten()

                # update data and metadata dicts depending on declared params
                return_img.update(
                    {parameter: param_data[self.grid.activegpis]})
                return_metadata.update({parameter: param_metadata})

                # Check for corrupt files
                try:
                    return_img[parameter]
                except KeyError:
                    path, file_name = os.path.split(self.filename)
                    print('%s in %s is corrupt - filling image with NaN values' % (parameter, file_name))
                    return_img[parameter] = np.empty(
                        self.grid.n_gpi).fill(np.nan)
                    return_metadata['corrupt_parameters'].append()

        if self.array_1D:
            return Image(self.grid.activearrlon,
                         self.grid.activearrlat,
                         return_img,
                         return_metadata,
                         timestamp)
        else:
            # iterate trough return_img dict and reshape nd-array to 361 x 576
            # matrix
            for key in return_img:
                print(key)
                return_img[key] = np.flipud(
                    return_img[key].reshape((361, 576)))

            # return Image object for called parameters
            return Image(np.flipud(self.grid.activearrlon.reshape((361, 576))),
                         np.flipud(self.grid.activearrlat.reshape((361, 576))),
                         return_img,
                         return_metadata,
                         timestamp)

    def write(self, image, **kwargs):
        """
        Write data to an image file.

        Parameters
        ----------
        image : object
            pygeobase.object_base.Image object
        """
        raise NotImplementedError()
        pass

    def flush(self):
        """
        Flush data.
        """
        pass

    def close(self):
        """
        Close file.
        """
        pass


class MERRA2_Ds_monthly(MultiTemporalImageBase):
    """
    Class for reading the monthly merra2 data. Read image stack between
    start date and end date under a given path.
    """

    def __init__(self, data_path, parameter='SFMC', array_1D=False):
        """
        Initialize MERRA2_Ds object with a given path.

        Parameters
        ----------
        data_path : string
            path to the nc files
        parameter : string or list, optional
            one or list of parameters to read, see MERRA2 documentation for more information
            Default : 'SFMC'
        array_1D: boolean, optional
            if set then the data is read into 1D arrays. Needed for some legacy code.
        """

        ioclass_kws = {'parameter': parameter,
                       'array_1D': array_1D}

        # define sub paths of root folder
        sub_path = ['%Y']

        # define fn template
        fn_template = "MERRA2_*.tavgM_2d_lnd_Nx.{datetime}.nc4"

        super(MERRA2_Ds_monthly, self).__init__(path=data_path,
                                                ioclass=MERRA_Img_m,
                                                fname_templ=fn_template,
                                                # monthly data
                                                datetime_format="%Y%m",
                                                subpath_templ=sub_path,
                                                exact_templ=False,
                                                ioclass_kws=ioclass_kws)

    def tstamps_for_daterange(self, start_date, end_date):
        """
        Return timestamps for a given date range.

        Parameters
        ----------
        start_date: datetime.datetime
            start of date range
        end_date: datetime.datetime
            end of date range

        Returns
        -------
        timestamps : list
            list of datetime objects of each available image between
            start_date and end_date
        """
        # initialize timestamp array, calculate nr of months between start and
        # end date
        timestamps = []
        diff = monthdelta.monthmod(start_date, end_date)[
            0] + monthdelta.monthdelta(1)

        for m in range(diff.months):
            # populate array month by month
            monthly_date = start_date + monthdelta.monthdelta(m)
            timestamps.append(monthly_date)

        return timestamps


class MERRA2_Ds(MultiTemporalImageBase):
    """
    Class for reading the hourly merra2 data. Read image stack between
    start date and end date under a given path.
    """
    def __init__(self, data_path, parameter='SFMC',
                 temporal_sampling=6, array_1D=False):
        """
        Initialize MERRA2_Ds_1h object with a given path.

        Parameters
        ----------
        data_path : string
            path to the nc files
        parameter : string or list, optional
            one or list of parameters to read, see MERRA2 documentation for more information
            Default : 'SFMC'
        temporal_sampling: int in range (1, 24)
            When stacking, get an image every n hours where n=temporal_sampling. For example:
            if 1: return hourly sampled data -> hourly sampling
            if 6: return an image every 6 hours -> 6 hourly sampling
            if 24: return the 00:30 image of each day -> daily sampling
        array_1D: boolean, optional
            if set then the data is read into 1D arrays. Needed for some legacy code.
        """
        # temporal sampling parameter
        self.temporal_sampling = temporal_sampling

        ioclass_kws = {'parameter': parameter,
                       'array_1D': array_1D}

        # define sub paths of root folder
        sub_path = ['%Y', '%m']

        # define fn template for 1h data
        fn_template = "MERRA2_*.tavg1_2d_lnd_Nx.{datetime}.nc4"

        super(MERRA2_Ds, self).__init__(path=data_path,
                                        ioclass=MERRA_Img,
                                        fname_templ=fn_template,
                                        # hourly data
                                               datetime_format="%Y%m%d",
                                        subpath_templ=sub_path,
                                        exact_templ=False,
                                        ioclass_kws=ioclass_kws)

    def tstamps_for_daterange(self, start_date, end_date):
        """
        Return timestamps for a given date range.

        Parameters
        ----------
        start_date: datetime.datetime
            start of date range
        end_date: datetime.datetime
            end of date range

        Returns
        -------
        timestamps : list
            list of datetime objects of each available image between
            start_date and end_date
        """
        # get every nth element where n is specified by "temporal_sampling"
        img_offsets = np.array([timedelta(hours=i, minutes=30)
                                for i in list(range(24))[::self.temporal_sampling]])

        timestamps = []
        diff = end_date - start_date
        for i in range(diff.days + 1):
            daily_dates = start_date + timedelta(days=i) + img_offsets
            timestamps.extend(daily_dates.tolist())

        return timestamps


class MERRA2_Ts(GriddedNcOrthoMultiTs):
    """
    Read MERRA2 time series data under a given path.
    """
    def __init__(self, ts_path=None, grid_path=None, **kwargs):
        """
        Initialize MERRA2_Ts object with path to data repository. Use to read
        time series data at a given location.

        Parameters
        ----------
        ts_path : string
            path to the nc file directory
        grid_path : string
            path to grid.nc file

        Optional keyword arguments that are passed to the Gridded Base:
        ------------------------------------------------------------------------
        parameters : list, optional (default: None)
            Specific variable names to read, if None are selected, all are read.
        ioclass_kws: dict

        Optional keyword arguments to pass to OrthoMultiTs class:
        ----------------------------------------------------------------
            read_bulk : boolean, optional (default:False)
                if set to True the data of all locations is read into memory,
                and subsequent calls to read_ts read from the cache and not from disk
                this makes reading complete files faster
            read_dates : boolean, optional (default:False)
                if false dates will not be read automatically but only on specific
                request useable for bulk reading because currently the netCDF
                num2date routine is very slow for big datasets
        """

        if grid_path is None:
            grid_path = os.path.join(ts_path, "grid.nc")

        grid = pygeogrids.netcdf.load_grid(grid_path)
        super(MERRA2_Ts, self).__init__(ts_path, grid, **kwargs)


if __name__ == '__main__':
    import matplotlib.pyplot as plt

    # specify path to data folder
    path = '/home/fzaussin/shares/radar/Datapool_processed/Earth2Observe/MERRA2/datasets/M2T1NXLND.5.12.4_6hourly'

    # find gpi for given lon and lat
    lon, lat = (16.375, 48.125)

    # read data
    merra_reader = MERRA2_Ts(ts_path=path,
                             ioclass_kws={'read_bulk':True},
                             parameters=['SFMC'])
    ts = merra_reader.read(lon, lat)
    ts.plot(figsize=(20, 10), subplots=True)

    # show plot
    plt.tight_layout()
    plt.show()