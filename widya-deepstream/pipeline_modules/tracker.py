import gi
import sys
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst

import configparser

class Tracker: 
    def __init__(
            self, 
            tracker_config_path : str, 
            pipeline
    ):
        self.tracker_config_path = tracker_config_path 
        self.pipeline = pipeline 
    
    def create_element(self, factory_name : str, name : str): 
        element = Gst.ElementFactory.make(factory_name, name)
        if not element:
            sys.stderr.write(" Unable to create Source \n")
        self.pipeline.add(element)
        return element

    def tracker_create_element(self): 
        print("make tracker")
        self.tracker_elm = self.create_element("nvtracker", "tracker")

        config = configparser.ConfigParser()
        config.read(self.tracker_config_path)
        config.sections()

        for key in config['tracker']:
            if key == 'tracker-width' :
                tracker_width = config.getint('tracker', key)
                self.tracker_elm.set_property('tracker-width', tracker_width)
            if key == 'tracker-height' :
                tracker_height = config.getint('tracker', key)
                self.tracker_elm.set_property('tracker-height', tracker_height)
            if key == 'gpu-id' :
                tracker_gpu_id = config.getint('tracker', key)
                self.tracker_elm.set_property('gpu_id', tracker_gpu_id)
            if key == 'll-lib-file' :
                tracker_ll_lib_file = config.get('tracker', key)
                self.tracker_elm.set_property('ll-lib-file', tracker_ll_lib_file)
            if key == 'll-config-file' :
                tracker_ll_config_file = config.get('tracker', key)
                self.tracker_elm.set_property('ll-config-file', tracker_ll_config_file)

        return [self.tracker_elm]

