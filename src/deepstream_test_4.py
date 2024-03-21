import sys
import pyds

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst

from optparse import OptionParser
from common.is_aarch_64 import is_aarch64
from common.bus_call import bus_call
from common.utils import long_to_uint64 


class DeepStreamApp4: 
    def __init__(
        self, 
        adaptor_config_file : str, 
        pgie_config_file : str,
        msconv_config_file : str,
        input_file : str, 

        proto_lib : str, 
        conn_str : str, 
        schema_type : int, 
        topic : str, 
        no_display : bool, 

        pgie_class_id_vehicle : int = 0,
        pgie_class_id_bicycle : int = 1,
        pgie_class_id_person : int = 2, 
        pgie_class_id_roadsign : int = 3, 
        muxer_batch_timeout_usec : int = 33000,
        max_time_stamp_len : int = 32, 

        pgie_classes_str : list = ["Vehicle", "TwoWheeler", "Person", "Roadsign"]
        ) -> None:
        self.adaptor_config_file = adaptor_config_file
        self.pgie_config_file = pgie_config_file 
        self.msconv_config_file = msconv_config_file 
        self.input_file = input_file

        self.proto_lib = proto_lib 
        self.conn_str = conn_str 
        self.schema_type = schema_type 
        self.topic = topic 
        self.no_display = no_display

        self.pgie_class_id_vehicle = pgie_class_id_vehicle 
        self.pgie_class_id_bicycle = pgie_class_id_bicycle
        self.pgie_class_id_person = pgie_class_id_person
        self.pgie_class_id_roadsign = pgie_class_id_roadsign 
        self.muxer_batch_timeout_usec = muxer_batch_timeout_usec
        self.max_time_stamp_len = max_time_stamp_len

        self.pgie_classes_str = pgie_classes_str

    def setup(self): 
        Gst.init(None)

        print("Creating Pipeline \n ")
        self.pipeline = Gst.Pipeline()

        if not self.pipeline:
            sys.stderr.write(" Unable to create Pipeline \n")

        print("Creating Source \n ")
        source = Gst.ElementFactory.make("filesrc", "file-source")
        if not source:
            sys.stderr.write(" Unable to create Source \n")

        print("Creating H264Parser \n")
        h264parser = Gst.ElementFactory.make("h264parse", "h264-parser")
        if not h264parser:
            sys.stderr.write(" Unable to create h264 parser \n")

        print("Creating Decoder \n")
        decoder = Gst.ElementFactory.make("nvv4l2decoder", "nvv4l2-decoder")
        if not decoder:
            sys.stderr.write(" Unable to create Nvv4l2 Decoder \n")

        streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
        if not streammux:
            sys.stderr.write(" Unable to create NvStreamMux \n")

        pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
        if not pgie:
            sys.stderr.write(" Unable to create pgie \n")

        nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "convertor")
        if not nvvidconv:
            sys.stderr.write(" Unable to create nvvidconv \n")

        self.nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")
        if not self.nvosd:
            sys.stderr.write(" Unable to create nvosd \n")

        msgconv = Gst.ElementFactory.make("nvmsgconv", "nvmsg-converter")
        if not msgconv:
            sys.stderr.write(" Unable to create msgconv \n")

        msgbroker = Gst.ElementFactory.make("nvmsgbroker", "nvmsg-broker")
        if not msgbroker:
            sys.stderr.write(" Unable to create msgbroker \n")

        tee = Gst.ElementFactory.make("tee", "nvsink-tee")
        if not tee:
            sys.stderr.write(" Unable to create tee \n")

        queue1 = Gst.ElementFactory.make("queue", "nvtee-que1")
        if not queue1:
            sys.stderr.write(" Unable to create queue1 \n")

        queue2 = Gst.ElementFactory.make("queue", "nvtee-que2")
        if not queue2:
            sys.stderr.write(" Unable to create queue2 \n")

        if self.no_display:
            print("Creating FakeSink \n")
            sink = Gst.ElementFactory.make("fakesink", "fakesink")
            if not sink:
                sys.stderr.write(" Unable to create fakesink \n")
        else:
            if is_aarch64():
                print("Creating nv3dsink \n")
                sink = Gst.ElementFactory.make("nv3dsink", "nv3d-sink")
                if not sink:
                    sys.stderr.write(" Unable to create nv3dsink \n")
            else:
                print("Creating EGLSink \n")
                # sink = Gst.ElementFactory.make("nveglglessink", "nvvideo-renderer")
                sink = Gst.ElementFactory.make("fakesink", "nvvideo-renderer")
                if not sink:
                    sys.stderr.write(" Unable to create egl sink \n")

        print("Playing file %s " % self.input_file)
        source.set_property('location', self.input_file)
        streammux.set_property('width', 1920)
        streammux.set_property('height', 1080)
        streammux.set_property('batch-size', 1)
        streammux.set_property('batched-push-timeout', self.muxer_batch_timeout_usec)
        pgie.set_property('config-file-path', self.pgie_config_file)
        msgconv.set_property('config', self.msconv_config_file)
        msgconv.set_property('payload-type', self.schema_type)
        msgbroker.set_property('proto-lib', self.proto_lib)
        msgbroker.set_property('conn-str', self.conn_str)
        if self.adaptor_config_file is not None:
            msgbroker.set_property('config', self.adaptor_config_file)
        if self.topic is not None:
            msgbroker.set_property('topic', self.topic)
        msgbroker.set_property('sync', False)

        print("Adding elements to Pipeline \n")
        self.pipeline.add(source)
        self.pipeline.add(h264parser)
        self.pipeline.add(decoder)
        self.pipeline.add(streammux)
        self.pipeline.add(pgie)
        self.pipeline.add(nvvidconv)
        self.pipeline.add(self.nvosd)
        self.pipeline.add(tee)
        self.pipeline.add(queue1)
        self.pipeline.add(queue2)
        self.pipeline.add(msgconv)
        self.pipeline.add(msgbroker)
        self.pipeline.add(sink)

        print("Linking elements in the Pipeline \n")
        source.link(h264parser)
        h264parser.link(decoder)

        sinkpad = streammux.get_request_pad("sink_0")
        if not sinkpad:
            sys.stderr.write(" Unable to get the sink pad of streammux \n")
        srcpad = decoder.get_static_pad("src")
        if not srcpad:
            sys.stderr.write(" Unable to get source pad of decoder \n")
        srcpad.link(sinkpad)

        streammux.link(pgie)
        pgie.link(nvvidconv)
        nvvidconv.link(self.nvosd)
        self.nvosd.link(tee)
        queue1.link(msgconv)
        msgconv.link(msgbroker)
        queue2.link(sink)
        sink_pad = queue1.get_static_pad("sink")
        tee_msg_pad = tee.get_request_pad('src_%u')
        tee_render_pad = tee.get_request_pad("src_%u")
        if not tee_msg_pad or not tee_render_pad:
            sys.stderr.write("Unable to get request pads\n")
        tee_msg_pad.link(sink_pad)
        sink_pad = queue2.get_static_pad("sink")
        tee_render_pad.link(sink_pad)

    def run(self): 
        # create an event loop and feed gstreamer bus messages to it
        loop = GLib.MainLoop()
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", bus_call, loop)

        osdsinkpad = self.nvosd.get_static_pad("sink")
        if not osdsinkpad:
            sys.stderr.write(" Unable to get sink pad of nvosd \n")

        osdsinkpad.add_probe(
            Gst.PadProbeType.BUFFER, 
            self.osd_sink_pad_buffer_probe, 
            0
        )

        print("Starting pipeline \n")

        # start play back and listed to events
        self.pipeline.set_state(Gst.State.PLAYING)
        try:
            loop.run()
        except:
            pass
        # cleanup
    
        #pyds.unset_callback_funcs()
        self.pipeline.set_state(Gst.State.NULL)
    
    def generate_vehicle_meta(self, data):
        obj = pyds.NvDsVehicleObject.cast(data)
        obj.type = "sedan"
        obj.color = "blue"
        obj.make = "Bugatti"
        obj.model = "M"
        obj.license = "XX1234"
        obj.region = "CA"
        return obj

    def generate_person_meta(self, data):
        obj = pyds.NvDsPersonObject.cast(data)
        obj.age = 45
        obj.cap = "none"
        obj.hair = "black"
        obj.gender = "male"
        obj.apparel = "formal"
        return obj

    def generate_event_msg_meta(self, data, class_id):
        meta = pyds.NvDsEventMsgMeta.cast(data)
        meta.sensorId = 0
        meta.placeId = 0
        meta.moduleId = 0
        meta.sensorStr = "sensor-0"
        meta.ts = pyds.alloc_buffer(self.max_time_stamp_len + 1)
        pyds.generate_ts_rfc3339(meta.ts, self.max_time_stamp_len)

        if class_id == self.pgie_class_id_vehicle:
            meta.type = pyds.NvDsEventType.NVDS_EVENT_MOVING
            meta.objType = pyds.NvDsObjectType.NVDS_OBJECT_TYPE_VEHICLE
            meta.objClassId = self.pgie_class_id_vehicle
            obj = pyds.alloc_nvds_vehicle_object()
            obj = self.generate_vehicle_meta(obj)
            meta.extMsg = obj
            meta.extMsgSize = sys.getsizeof(pyds.NvDsVehicleObject)

        if class_id == self.pgie_class_id_person:
            meta.type = pyds.NvDsEventType.NVDS_EVENT_ENTRY
            meta.objType = pyds.NvDsObjectType.NVDS_OBJECT_TYPE_PERSON
            meta.objClassId = self.pgie_class_id_person
            obj = pyds.alloc_nvds_person_object()
            obj = self.generate_person_meta(obj)
            meta.extMsg = obj
            meta.extMsgSize = sys.getsizeof(pyds.NvDsPersonObject)
        return meta

    def osd_sink_pad_buffer_probe(self, pad, info, u_data):
        frame_number = 0
        # Intiallizing object counter with 0.
        obj_counter = {
            self.pgie_class_id_vehicle:0,
            self.pgie_class_id_bicycle:0,
            self.pgie_class_id_person:0,
            self.pgie_class_id_roadsign:0
        }
        gst_buffer = info.get_buffer()
        if not gst_buffer:
            print("Unable to get GstBuffer ")
            return

        # Retrieve batch metadata from the gst_buffer
        # Note that pyds.gst_buffer_get_nvds_batch_meta() expects the
        # C address of gst_buffer as input, which is obtained with hash(gst_buffer)
        batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
        if not batch_meta:
            return Gst.PadProbeReturn.OK
        l_frame = batch_meta.frame_meta_list
        while l_frame is not None:
            try:
                # Note that l_frame.data needs a cast to pyds.NvDsFrameMeta
                # The casting is done by pyds.NvDsFrameMeta.cast()
                # The casting also keeps ownership of the underlying memory
                # in the C code, so the Python garbage collector will leave
                # it alone.
                frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
            except StopIteration:
                continue
            is_first_object = True

            frame_number = frame_meta.frame_num
            l_obj = frame_meta.obj_meta_list
            while l_obj is not None:
                try:
                    obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
                except StopIteration:
                    continue

                # Update the object text display
                txt_params = obj_meta.text_params

                # Set display_text. Any existing display_text string will be
                # freed by the bindings module.
                txt_params.display_text = self.pgie_classes_str[obj_meta.class_id]

                obj_counter[obj_meta.class_id] += 1

                # Font , font-color and font-size
                txt_params.font_params.font_name = "Serif"
                txt_params.font_params.font_size = 10
                # set(red, green, blue, alpha); set to White
                txt_params.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)

                # Text background color
                txt_params.set_bg_clr = 1
                # set(red, green, blue, alpha); set to Black
                txt_params.text_bg_clr.set(0.0, 0.0, 0.0, 1.0)

                # Ideally NVDS_EVENT_MSG_META should be attached to buffer by the
                # component implementing detection / recognition logic.
                # Here it demonstrates how to use / attach that meta data.
                if is_first_object and (frame_number % 30) == 0:
                    # Frequency of messages to be send will be based on use case.
                    # Here message is being sent for first object every 30 frames.

                    user_event_meta = pyds.nvds_acquire_user_meta_from_pool(
                        batch_meta)
                    if user_event_meta:
                        # Allocating an NvDsEventMsgMeta instance and getting
                        # reference to it. The underlying memory is not manged by
                        # Python so that downstream plugins can access it. Otherwise
                        # the garbage collector will free it when this probe exits.
                        msg_meta = pyds.alloc_nvds_event_msg_meta(user_event_meta)
                        msg_meta.bbox.top = obj_meta.rect_params.top
                        msg_meta.bbox.left = obj_meta.rect_params.left
                        msg_meta.bbox.width = obj_meta.rect_params.width
                        msg_meta.bbox.height = obj_meta.rect_params.height
                        msg_meta.frameId = frame_number
                        msg_meta.trackingId = long_to_uint64(obj_meta.object_id)
                        msg_meta.confidence = obj_meta.confidence
                        msg_meta = self.generate_event_msg_meta(msg_meta, obj_meta.class_id)

                        user_event_meta.user_meta_data = msg_meta
                        user_event_meta.base_meta.meta_type = pyds.NvDsMetaType.NVDS_EVENT_MSG_META
                        pyds.nvds_add_user_meta_to_frame(frame_meta,
                                                         user_event_meta)
                    else:
                        print("Error in attaching event meta to buffer\n")

                    is_first_object = False
                try:
                    l_obj = l_obj.next
                except StopIteration:
                    break
            try:
                l_frame = l_frame.next
            except StopIteration:
                break

        print("Frame Number =", frame_number, "Vehicle Count =",
            obj_counter[self.pgie_class_id_vehicle], "Person Count =",
            obj_counter[self.pgie_class_id_person])
        return Gst.PadProbeReturn.OK
    
if __name__ == "__main__": 
    import argparse 
    parser = argparse.ArgumentParser(description="Deepstream test-app 4") 
    parser.add_argument(
        "--adaptor-cfg", 
        dest="adaptor_cfg",
        help="Set the adaptor config file. Optional if "
             "connection string has relevant  details.",
        metavar="FILE", 
        default=None
        )
    parser.add_argument(
        "--pgie-cfg", 
        dest="pgie_cfg", 
        metavar="FILE", 
        default="configs/pgies/dstest4_pgie_config.txt"
        )
    parser.add_argument(
        "--msconv-cfg", 
        dest="msconv_cfg", 
        metavar="FILE",
        default="configs/dstest4_msgconv_config.txt"
        )
    parser.add_argument(
        "--input-file", 
        dest="input_file", 
        help="Set the input H264 file", 
        metavar="FILE",
        default="/opt/nvidia/deepstream/deepstream/samples/streams/sample_720p.h264"
        )
    parser.add_argument(
        "--proto-lib", 
        dest="proto_lib", 
        help="Absolute path of adaptor library", 
        metavar="PATH",
        default="/opt/nvidia/deepstream/deepstream-6.4/lib/libnvds_redis_proto.so"
        )
    parser.add_argument(
        "--conn-str", 
        dest="conn_str",
        help="Connection string of backend server. Optional if "
             "it is part of config file.", 
        metavar="STR", 
        default="localhost;6379"
        )
    parser.add_argument(
        "--schema-type", 
        dest="schema_type", 
        default=0,
        help="Type of message schema (0=Full, 1=minimal), "
             "default=0", 
        metavar="<0|1>", 
        )
    parser.add_argument(
        "--topic",
        dest="topic", 
        help="Name of message topic. Optional if it is part of "
             "connection string or config file.", 
        metavar="TOPIC",
        default=None
        )
    parser.add_argument(
        "--no-display", 
        dest="no_display", 
        action="store_true",
        default=False,
        help="Disable display", 
    )

    args = parser.parse_args()

    pipeline = DeepStreamApp4(
        args.adaptor_cfg,
        args.pgie_cfg,
        args.msconv_cfg, 
        args.input_file, 
        args.proto_lib, 
        args.conn_str, 
        args.schema_type, 
        args.topic,
        args.no_display
    )
    pipeline.setup()
    pipeline.run()
