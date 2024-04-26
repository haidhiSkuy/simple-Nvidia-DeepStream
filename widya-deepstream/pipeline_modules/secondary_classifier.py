import gi
import sys
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst

class SecondaryClassifier: 
    def __init__(
            self, 
            sgie_config_path1 : str, 
            sgie_config_path2 : str,
            pipeline
    ):
        self.sgie_config_path1 = sgie_config_path1
        self.sgie_config_path2 = sgie_config_path2 
        self.pipeline = pipeline 
    
    def create_element(self, factory_name : str, name : str): 
        element = Gst.ElementFactory.make(factory_name, name)
        if not element:
            sys.stderr.write(" Unable to create Source \n")
        self.pipeline.add(element)
        return element

    def sgie_create_element(self): 
        print("make sgie")
        self.sgie1 = self.create_element("nvinfer", "secondary1-nvinference-engine")
        self.sgie1.set_property('config-file-path', self.sgie_config_path1)

        self.sgie2 = self.create_element("nvinfer", "secondary2-nvinference-engine") 
        self.sgie2.set_property('config-file-path', self.sgie_config_path2) 
        return [self.sgie1, self.sgie2]

