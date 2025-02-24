"""Utility functions used in the morphology subpackage."""


import numpy as np
from scipy import ndimage as ndi


def _validate_connectivity(image_dim, connectivity, offset):
    """Convert any valid connectivity to a footprint and offset.

    Parameters
    ----------
    image_dim : int
        The number of dimensions of the input image.
    connectivity : int, array, or None
        The neighborhood connectivity. An integer is interpreted as in
        ``scipy.ndimage.generate_binary_structure``, as the maximum number
        of orthogonal steps to reach a neighbor. An array is directly
        interpreted as a footprint and its shape is validated against
        the input image shape. ``None`` is interpreted as a connectivity of 1.
    offset : tuple of int, or None
        The coordinates of the center of the footprint.

    Returns
    -------
    c_connectivity : array of bool
        The footprint (structuring element) corresponding to the input
        `connectivity`.
    offset : array of int
        The offset corresponding to the center of the footprint.

    Raises
    ------
    ValueError:
        If the image dimension and the connectivity or offset dimensions don't
        match.
    """
    if connectivity is None:
        connectivity = 1

    if np.isscalar(connectivity):
        c_connectivity = ndi.generate_binary_structure(image_dim, connectivity)
    else:
        c_connectivity = np.array(connectivity, bool)
        if c_connectivity.ndim != image_dim:
            raise ValueError("Connectivity dimension must be same as image")

    if offset is None:
        if any([x % 2 == 0 for x in c_connectivity.shape]):
            raise ValueError("Connectivity array must have an unambiguous "
                             "center")

        offset = np.array(c_connectivity.shape) // 2

    return c_connectivity, offset


def _offsets_to_raveled_neighbors(image_shape, footprint, center, order='C'):
    """Compute offsets to a samples neighbors if the image would be raveled.

    Parameters
    ----------
    image_shape : tuple
        The shape of the image for which the offsets are computed.
    footprint : ndarray
        The footprint (structuring element) determining the neighborhood
        expressed as an n-D array of 1's and 0's.
    center : tuple
        Tuple of indices to the center of `footprint`.
    order : {"C", "F"}, optional
        Whether the image described by `image_shape` is in row-major (C-style)
        or column-major (Fortran-style) order.

    Returns
    -------
    raveled_offsets : ndarray
        Linear offsets to a samples neighbors in the raveled image, sorted by
        their distance from the center.

    Notes
    -----
    This function will return values even if `image_shape` contains a dimension
    length that is smaller than `footprint`.

    Examples
    --------
    >>> _offsets_to_raveled_neighbors((4, 5), np.ones((4, 3)), (1, 1))
    array([-5, -1,  1,  5, -6, -4,  4,  6, 10,  9, 11])
    >>> _offsets_to_raveled_neighbors((2, 3, 2), np.ones((3, 3, 3)), (1, 1, 1))
    array([ 2, -6,  1, -1,  6, -2,  3,  8, -3, -4,  7, -5, -7, -8,  5,  4, -9,
            9])
    """
    if not footprint.ndim == len(image_shape) == len(center):
        raise ValueError(
            "number of dimensions in image shape, footprint and its"
            "center index does not match"
        )

    footprint_indices = np.stack(np.nonzero(footprint), axis=-1)
    offsets = footprint_indices - center

    if order == 'F':
        offsets = offsets[:, ::-1]
        image_shape = image_shape[::-1]
    elif order != 'C':
        raise ValueError("order must be 'C' or 'F'")

    # Scale offsets in each dimension and sum
    ravel_factors = image_shape[1:] + (1,)
    ravel_factors = np.cumprod(ravel_factors[::-1])[::-1]
    raveled_offsets = (offsets * ravel_factors).sum(axis=1)

    # Sort by distance
    distances = np.abs(offsets).sum(axis=1)
    raveled_offsets = raveled_offsets[np.argsort(distances)]

    # If any dimension in image_shape is smaller than footprint.shape
    # duplicates might occur, remove them
    if any(x < y for x, y in zip(image_shape, footprint.shape)):
        # np.unique reorders, which we don't want
        _, indices = np.unique(raveled_offsets, return_index=True)
        raveled_offsets = raveled_offsets[np.sort(indices)]

    # Remove "offset to center"
    raveled_offsets = raveled_offsets[1:]

    return raveled_offsets


def _resolve_neighborhood(footprint, connectivity, ndim):
    """Validate or create a footprint (structuring element).

    Depending on the values of `connectivity` and `footprint` this function
    either creates a new footprint (`footprint` is None) using `connectivity`
    or validates the given footprint (`footprint` is not None).

    Parameters
    ----------
    footprint : ndarray
        The footprint (structuring) element used to determine the neighborhood
        of each evaluated pixel (``True`` denotes a connected pixel). It must
        be a boolean array and have the same number of dimensions as `image`.
        If neither `footprint` nor `connectivity` are given, all adjacent
        pixels are considered as part of the neighborhood.
    connectivity : int
        A number used to determine the neighborhood of each evaluated pixel.
        Adjacent pixels whose squared distance from the center is less than or
        equal to `connectivity` are considered neighbors. Ignored if
        `footprint` is not None.
    ndim : int
        Number of dimensions `footprint` ought to have.

    Returns
    -------
    footprint : ndarray
        Validated or new footprint specifying the neighborhood.

    Examples
    --------
    >>> _resolve_neighborhood(None, 1, 2)
    array([[False,  True, False],
           [ True,  True,  True],
           [False,  True, False]])
    >>> _resolve_neighborhood(None, None, 3).shape
    (3, 3, 3)
    """
    if footprint is None:
        if connectivity is None:
            connectivity = ndim
        footprint = ndi.generate_binary_structure(ndim, connectivity)
    else:
        # Validate custom structured element
        footprint = np.asarray(footprint, dtype=bool)
        # Must specify neighbors for all dimensions
        if footprint.ndim != ndim:
            raise ValueError(
                "number of dimensions in image and footprint do not"
                "match"
            )
        # Must only specify direct neighbors
        if any(s != 3 for s in footprint.shape):
            raise ValueError("dimension size in footprint is not 3")

    return footprint


def _set_border_values(image, value):
    """Set edge values along all axes to a constant value.

    Parameters
    ----------
    image : ndarray
        The array to modify inplace.
    value : scalar
        The value to use. Should be compatible with `image`'s dtype.

    Examples
    --------
    >>> image = np.zeros((4, 5), dtype=int)
    >>> _set_border_values(image, 1)
    >>> image
    array([[1, 1, 1, 1, 1],
           [1, 0, 0, 0, 1],
           [1, 0, 0, 0, 1],
           [1, 1, 1, 1, 1]])
    """
    for axis in range(image.ndim):
        # Index first and last element in each dimension
        sl = (slice(None),) * axis + ((0, -1),) + (...,)
        image[sl] = value
