"""
Built-in instrument configurations for SAXS and WAXS.

Each configuration maps parameter names to HDF5 paths / metadata keys and
EPICS PV names.  Custom instruments store the same structure in a JSON file.
"""

INSTRUMENT_CONFIGS: dict[str, dict] = {
    "SAXS": {
        "calibrant": "AgBehenate",
        "hdf5": {
            "data_path": "/entry/data/data",
            "sdd": ("instrument", "detector", "distance"),
            "pixel_size": ("instrument", "detector", "x_pixel_size"),
            "wavelength": ("instrument", "monochromator", "wavelength"),
            "bcx_metadata_key": "pin_ccd_center_x_pixel",
            "bcy_metadata_key": "pin_ccd_center_y_pixel",
            "tilt_x_metadata_key": "pin_ccd_tilt_x",
            "tilt_y_metadata_key": "pin_ccd_tilt_y",
        },
        "epics": {
            "bcx": "usxLAX:SAXS:BeamCenterX",
            "bcy": "usxLAX:SAXS:BeamCenterY",
            "tilt_x": "usxLAX:SAXS:DetectorTiltX",
            "tilt_y": "usxLAX:SAXS:DetectorTiltY",
            "sdd": "usxLAX:SAXS:Distance",
            "report": "usxLAX:SAXS:CalibrationReport",
        },
        "mask": {
            "type": "saxs",          # negative pixels → masked (Eiger/Pilatus)
            "dead_columns": [[0, 4], [242, 245]],
        },
    },
    "WAXS": {
        "calibrant": "LaB6",
        "hdf5": {
            "data_path": "/entry/data/data",
            "sdd": ("instrument", "detector", "distance"),
            "pixel_size": ("instrument", "detector", "x_pixel_size"),
            "wavelength": ("instrument", "monochromator", "wavelength"),
            "bcx_metadata_key": "waxs_ccd_center_x_pixel",
            "bcy_metadata_key": "waxs_ccd_center_y_pixel",
            "tilt_x_metadata_key": "waxs_ccd_tilt_x",
            "tilt_y_metadata_key": "waxs_ccd_tilt_y",
        },
        "epics": {
            "bcx": "usxLAX:WAXS:BeamCenterX",
            "bcy": "usxLAX:WAXS:BeamCenterY",
            "tilt_x": "usxLAX:WAXS:DetectorTiltX",
            "tilt_y": "usxLAX:WAXS:DetectorTiltY",
            "sdd": "usxLAX:WAXS:Distance",
            "report": "usxLAX:WAXS:CalibrationReport",
        },
        "mask": {
            "type": "waxs",          # values > 1e7 → masked (Pilatus gaps)
            "dead_columns": [[511, 516], [1026, 1041], [1551, 1556]],
        },
    },
}
