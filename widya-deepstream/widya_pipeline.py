import os
import sys
import math
from typing import List
from collections import defaultdict
from inspect import signature
from functools import partial
from custom_nvods import CustomNvosd

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst

import pyds
from common.bus_call import bus_call
from common.is_aarch_64 import is_aarch64  
from common.FPS import PERF_DATA, FPSMonitor
from common.label_list import get_label


class PipelineCommon: 
    def __init__(
            self,
            source_files : list[str],
            pgie_config_file : str,
            muxer_batch_timeout_usec : float = 33000,
            file_loop : bool = False, 

            disable_probe : bool = False,

            tiled_output_height : int = 1280,
            tiled_output_width : int = 720, 

            osd_process_mode : int = 0, 
            osd_display_text : int = 1,
    ): 
        self.source_files = source_files
        self.pgie_config_file = pgie_config_file 
        self.muxer_batch_timeout_usec = muxer_batch_timeout_usec
        self.file_loop = file_loop

        self.disable_probe = disable_probe

        self.tiled_output_width = tiled_output_width
        self.tiled_output_height = tiled_output_height

        self.osd_process_mode = osd_process_mode
        self.osd_display_text = osd_display_text

        # Pipeline
        Gst.init(None)
        self.pipeline = Gst.Pipeline()
        self.elements = []

        # fps
        self.fps_streams = {}
        for i in range(len(self.source_files)):
            self.fps_streams[f"stream{i}"] = FPSMonitor(i)

        self.custom_nvods = CustomNvosd(
            self.pgie_config_file, 
            self.fps_streams
            )

    ###### element methods #######
    def create_element(self, factory_name : str, name : str): 
        element = Gst.ElementFactory.make(factory_name, name)
        if not element:
            sys.stderr.write(" Unable to create Source \n")
        self.pipeline.add(element)
        return element

    def _link(self, elements : list): 
        print(' --> '.join(map(lambda x: x.name, elements)))
        for i in range(0, len(elements) - 1):
            elements[i].link(elements[i + 1])


    ###### Create source bin and streammux for handling input video ######
    def cb_newpad(self, decodebin, decoder_src_pad, data):
        print("In cb_newpad\n")
        caps = decoder_src_pad.get_current_caps()
        if not caps:
            caps = decoder_src_pad.query_caps()
        gststruct = caps.get_structure(0)
        gstname = gststruct.get_name()
        source_bin = data
        features = caps.get_features(0)

        # Need to check if the pad created by the decodebin is for video and not
        # audio.
        print("gstname=",gstname)
        if(gstname.find("video")!=-1):
            print("features=",features)
            if features.contains("memory:NVMM"):
                bin_ghost_pad=source_bin.get_static_pad("src")
                if not bin_ghost_pad.set_target(decoder_src_pad):
                    sys.stderr.write("Failed to link decoder src pad to source bin ghost pad\n")
            else:
                sys.stderr.write(" Error: Decodebin did not pick nvidia decoder plugin.\n")

    def decodebin_child_added(self, child_proxy, Object, name, user_data):
        print("Decodebin child added:", name, "\n")
        if name.find("decodebin") != -1:
            Object.connect("child-added", self.decodebin_child_added, user_data)
        
        if not is_aarch64() and name.find("nvv4l2decoder") != -1:
            Object.set_property("cudadec-memtype", 2)

        if "source" in name:
            source_element = child_proxy.get_by_name("source")
            if source_element.find_property('drop-on-latency') != None:
                Object.set_property("drop-on-latency", True)

    def create_source_bin(self, index, uri):
        # Create a source GstBin to abstract this bin's content from the rest of the
        # pipeline
        bin_name = "source-bin-%02d" %index
        print("creating",bin_name)
        nbin = Gst.Bin.new(bin_name)
        if not nbin:
            sys.stderr.write(" Unable to create source bin \n")

        uri_decode_bin = Gst.ElementFactory.make("uridecodebin", "uri-decode-bin")
        if not uri_decode_bin:
            sys.stderr.write(" Unable to create uri decode bin \n")
        # We set the input uri to the source element
        uri_decode_bin.set_property("uri",uri)
        # Connect to the "pad-added" signal of the decodebin which generates a
        # callback once a new pad for raw data has beed created by the decodebin
        uri_decode_bin.connect("pad-added", self.cb_newpad, nbin)
        uri_decode_bin.connect("child-added", self.decodebin_child_added, nbin)

        # We need to create a ghost pad for the source bin which will act as a proxy
        # for the video decoder src pad. The ghost pad will not have a target right
        # now. Once the decode bin creates the video decoder and generates the
        # cb_newpad callback, we will set the ghost pad target to the video decoder
        # src pad.
        Gst.Bin.add(nbin,uri_decode_bin)
        bin_pad = nbin.add_pad(Gst.GhostPad.new_no_target("src",Gst.PadDirection.SRC))
        if not bin_pad:
            sys.stderr.write(" Failed to add ghost pad in source bin \n")
            return None
        return nbin

    def create_streammux(self):
        streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
        if not streammux:
            sys.stderr.write(" Unable to create NvStreamMux \n")
        streammux.set_property('width', 1920)
        streammux.set_property('height', 1080)
        streammux.set_property('batch-size', len(self.source_files))
        streammux.set_property('batched-push-timeout', self.muxer_batch_timeout_usec)
        self.pipeline.add(streammux)
        return streammux
    
    def _get_video(self): 
        for i in range(len(self.source_files)):
            uri_name = self.source_files[i]
            if uri_name.find("rtsp://") == 0 :
                is_live = True
            source_bin = self.create_source_bin(i, uri_name)
            if not source_bin:
                sys.stderr.write("Unable to create source bin \n")
            self.pipeline.add(source_bin)
            padname = "sink_%u" %i
            sinkpad = self.streammux.get_request_pad(padname) 
            if not sinkpad:
                sys.stderr.write("Unable to create sink pad bin \n")
            srcpad = source_bin.get_static_pad("src")
            if not srcpad:
                sys.stderr.write("Unable to create src pad bin \n")
            srcpad.link(sinkpad)

    
    #### Nvods ####
    def _probe_fn_wrapper(self, _, info, probe_fn, get_frames=False):
        gst_buffer = info.get_buffer()
        if not gst_buffer:
            self.logger.error("Unable to get GstBuffer")
            return

        frames = []
        l_frame_meta = []
        ll_obj_meta = []
        batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
        l_frame = batch_meta.frame_meta_list
        while l_frame is not None:
            try:
                frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
            except StopIteration:
                break

            if get_frames:
                frame = pyds.get_nvds_buf_surface(hash(gst_buffer), frame_meta.batch_id)
                frames.append(frame)

            l_frame_meta.append(frame_meta)
            l_obj_meta = []

            l_obj = frame_meta.obj_meta_list
            while l_obj is not None:
                try:
                    obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
                except StopIteration:
                    break

                l_obj_meta.append(obj_meta)

                try:
                    l_obj = l_obj.next
                except StopIteration:
                    break

            ll_obj_meta.append(l_obj_meta)

            try:
                l_frame = l_frame.next
            except StopIteration:
                break

        if get_frames:
            probe_fn(frames, batch_meta, l_frame_meta, ll_obj_meta)
        else:
            probe_fn(batch_meta, l_frame_meta, ll_obj_meta)

        return Gst.PadProbeReturn.OK


    def _wrap_probe(self, probe_fn):
        get_frames = "frames" in signature(probe_fn).parameters
        return partial(self._probe_fn_wrapper, probe_fn=probe_fn, get_frames=get_frames)

    
    ###### Building pipeline ####### 
    def build_pipeline(self): 
        self.perf_data = PERF_DATA(len(self.source_files))
        number_sources = len(self.source_files)

        # Create nvstreammux instance to form batches from one or more sources.
        self.streammux = self.create_streammux()
        self._get_video()

        # Primary inferencer
        self.pgie = self.create_element("nvinfer", "primary-inference")
        self.pgie.set_property('config-file-path', self.pgie_config_file)
        self.pgie.set_property("batch-size", number_sources)

        # Converter
        self.nvvidconv1 = self.create_element("nvvideoconvert", "convertor1")
        self.caps1 = Gst.Caps.from_string("video/x-raw(memory:NVMM), format=RGBA")
        self.filter1 = self.create_element("capsfilter", "filter1")
        self.filter1.set_property("caps", self.caps1)

        self.tiler = self.create_element("nvmultistreamtiler", "nvtiler")
        tiler_rows = int(math.sqrt(number_sources))
        tiler_columns = int(math.ceil((1.0 * number_sources) / tiler_rows))
        self.tiler.set_property("rows", tiler_rows)
        self.tiler.set_property("columns", tiler_columns)
        self.tiler.set_property("width", 1920)
        self.tiler.set_property("height", 1080)

        self.nvvidconv = self.create_element("nvvideoconvert", "convertor")
        
        # nvosd
        self.nvosd = self.create_element("nvdsosd", "onscreendisplay")

        # sink
        self.sink = self.create_element("fakesink", "fakesink")
        self.sink.set_property("sync", 0)
        self.sink.set_property("qos", 0)

        if not is_aarch64():
            mem_type = int(pyds.NVBUF_MEM_CUDA_UNIFIED)
            self.streammux.set_property("nvbuf-memory-type", mem_type)
            self.nvvidconv.set_property("nvbuf-memory-type", mem_type)
            self.nvvidconv1.set_property("nvbuf-memory-type", mem_type)
            self.tiler.set_property("nvbuf-memory-type", mem_type)
        
    def linking_pipeline(self): 
        print("\033[1m"+"Linking elements in the Pipeline"+"\033[0m")
        # link the elements sequentially 
        elements = [
                self.streammux, 
                self.pgie, 
                self.nvvidconv1, 
                self.filter1, 
                self.tiler, 
                self.nvvidconv, 
                self.nvosd,
                self.sink
            ]
        
        self._link(elements)

    
    def run(self): 
        loop = GLib.MainLoop()
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect ("message", bus_call, loop)
        tiler_sink_pad = self.tiler.get_static_pad("sink")
        if not tiler_sink_pad:
            sys.stderr.write(" Unable to get src pad \n")
        else:
            if not self.disable_probe:
                # tiler_sink_pad.add_probe(
                #     Gst.PadProbeType.BUFFER, 
                #     self._wrap_probe(self.custom_nvods.write_osd_analytics))
                
                # tiler_sink_pad.add_probe(
                #     Gst.PadProbeType.BUFFER, 
                #     self._wrap_probe(self.custom_nvods.write_frame))
                
                tiler_sink_pad.add_probe(
                    Gst.PadProbeType.BUFFER, 
                    self._wrap_probe(self.custom_nvods.redis)
                    )

                # perf callback function to print fps every 5 sec
                GLib.timeout_add(1000, self.perf_data.perf_print_callback)

        # List the sources
        print("Now playing...")
        for i, source in enumerate(self.source_files):
            print(i, ": ", source)

        print("Starting pipeline \n")
        # start play back and listed to events		
        self.pipeline.set_state(Gst.State.PLAYING)
        try:
            loop.run()
        except:
            pass
        # cleanup
        print("Exiting app\n")
        self.pipeline.set_state(Gst.State.NULL) 